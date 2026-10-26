import os, sys, base64
os.environ.update({"APP_ENCRYPTION_KEY": base64.b64encode(os.urandom(32)).decode(), "BCRYPT_ROUNDS": "4"})
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
from datetime import timedelta
import mongomock, pyotp
import accounts as A, ratelimit as RL, mongo_init, settings_store as S

db = mongomock.MongoClient()["t"]
mongo_init.ensure_indexes(db)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)
def raises(code, fn, *a, **k):
    try: fn(*a, **k)
    except A.AuthError as e: return e.code == code
    return False

# ---- passwords
h = A.hash_password("a" * 100)
check(A.verify_password("a" * 100, h) and not A.verify_password("a" * 99 + "b", h), "long passwords are not truncated at 72 bytes")
check(A.verify_password("x", None) is False, "missing user still runs one comparison and says no")
check(raises("PASSWORD_TOO_SHORT", A.check_password_policy, db, "short"), "short password refused")
check(raises("PASSWORD_TOO_COMMON", A.check_password_policy, db, "password123"), "common password refused")
check(raises("PASSWORD_TOO_COMMON", A.check_password_policy, db, "fan.person99xx", "fan.person99xx@x.com"), "password equal to the e-mail name refused")

# ---- register, verify, sign in
check(raises("BAD_EMAIL", A.register, db, "nope", "long-enough-pw-1"), "bad e-mail refused")
u, tok = A.register(db, " Fan@Example.com ", "correct-horse-1", ip="1.1.1.1")
check(u and u["email"] == "fan@example.com" and tok, "register: e-mail normalised, verify token returned")
check(A.register(db, "fan@example.com", "correct-horse-1") == (None, None), "register: taken e-mail gives the same quiet result")
check("password_hash" in db.users.find_one({"id": u["id"]}) and db.users.find_one({"id": u["id"]})["password_hash"].startswith("$2"), "password stored as a bcrypt hash")
check(db.auth_tokens.find_one({"_id": tok}) is None and db.auth_tokens.count_documents({}) == 1, "token stored hashed, never raw")
check(raises("EMAIL_NOT_VERIFIED", A.login, db, "fan@example.com", "correct-horse-1"), "unverified e-mail cannot sign in")
check(raises("TOKEN_INVALID", A.verify_email, db, "garbage"), "bad verify token refused")
A.verify_email(db, tok)
check(raises("TOKEN_INVALID", A.verify_email, db, tok), "verify link works once only")
check(raises("BAD_CREDENTIALS", A.login, db, "ghost@example.com", "whatever-123"), "unknown user: same answer as wrong password")
check(raises("BAD_CREDENTIALS", A.login, db, "fan@example.com", "wrong-password"), "wrong password refused")
r = A.login(db, "FAN@example.com", "correct-horse-1", ip="2.2.2.2", ua="UA")
check(r["status"] == "ok" and r["scope"] == "full", "sign in ok")
user, sess = A.load_session(db, r["token"])
check(user and user["id"] == u["id"] and "password_hash" not in user and "totp" not in user, "session loads the user without secrets")
check(db.sessions.find_one({"_id": r["token"]}) is None, "session token is stored hashed")
check(A.load_session(db, "nope") == (None, None), "bad session token refused")
A.end_session(db, r["token"]); check(A.load_session(db, r["token"]) == (None, None), "sign out ends the session")
check(db.auth_log.count_documents({"event": "login", "ok": False}) >= 2, "failed sign-ins are logged")

# ---- lockout
S.put(db, "auth.max_failed_logins", 3)
for _ in range(3):
    try: A.login(db, "fan@example.com", "wrong-password")
    except A.AuthError: pass
check(raises("LOCKED", A.login, db, "fan@example.com", "correct-horse-1"), "locked after repeated failures, even with the right password")
db.users.update_one({"id": u["id"]}, {"$set": {"locked_until": A.utcnow() - timedelta(seconds=1)}})
check(A.login(db, "fan@example.com", "correct-horse-1")["status"] == "ok", "lock ends on time")

# ---- reset
t1 = A.login(db, "fan@example.com", "correct-horse-1")["token"]
check(A.request_reset(db, "ghost@example.com") == (None, None), "reset for unknown e-mail returns nothing")
_, rt = A.request_reset(db, "fan@example.com")
check(raises("PASSWORD_TOO_SHORT", A.confirm_reset, db, rt, "short"), "reset enforces the password rule")
check(A.peek_token(db, rt, "password_reset") is not None, "a refused reset does not use up the link")
A.confirm_reset(db, rt, "brand-new-pass-9")
check(raises("TOKEN_INVALID", A.confirm_reset, db, rt, "another-new-pass-9"), "reset link works once only")
check(A.load_session(db, t1) == (None, None), "reset signs out every device")
check(raises("BAD_CREDENTIALS", A.login, db, "fan@example.com", "correct-horse-1") and A.login(db, "fan@example.com", "brand-new-pass-9")["status"] == "ok", "old password dead, new one works")
_, rt2 = A.request_reset(db, "fan@example.com")
db.auth_tokens.update_one({"_id": A.sha(rt2)}, {"$set": {"expires_at": A.utcnow() - timedelta(seconds=1)}})
check(raises("TOKEN_INVALID", A.confirm_reset, db, rt2, "brand-new-pass-10"), "expired reset link refused")

# ---- change password / e-mail
a = A.login(db, "fan@example.com", "brand-new-pass-9")["token"]; b = A.login(db, "fan@example.com", "brand-new-pass-9")["token"]
check(raises("BAD_CREDENTIALS", A.change_password, db, u["id"], "nope", "xxxxxxxxxxxx1"), "change password needs the current one")
A.change_password(db, u["id"], "brand-new-pass-9", "third-pass-word-3", keep_token=a)
check(A.load_session(db, a)[0] and A.load_session(db, b) == (None, None), "change password signs out the other devices, keeps this one")
_, et = A.request_email_change(db, u["id"], "New@Example.com", "third-pass-word-3")
old, newu = A.confirm_email_change(db, et)
check(old == "fan@example.com" and newu["email"] == "new@example.com", "e-mail change confirmed from the new inbox")
check(raises("BAD_CREDENTIALS", A.request_email_change, db, u["id"], "x@example.com", "wrong"), "e-mail change needs the password")

# ---- two-factor
S.put(db, "auth.session_days", 30)
begin = A.twofa_begin(db, u["id"])
check("otpauth://" in begin["otpauth_uri"] and begin["secret"] not in str(db.users.find_one({"id": u["id"]})), "2FA secret stored encrypted")
check(raises("BAD_CODE", A.twofa_confirm, db, u["id"], "000000"), "wrong enrolment code refused")
codes = A.twofa_confirm(db, u["id"], pyotp.TOTP(begin["secret"]).now())
check(len(codes) == 10 and all(c not in str(db.users.find_one({"id": u["id"]})) for c in codes), "10 recovery codes shown once, stored hashed")
r = A.login(db, "new@example.com", "third-pass-word-3")
check(r["status"] == "needs_2fa" and "token" not in r, "password alone no longer signs in")
check(raises("BAD_CODE", A.login_2fa, db, r["challenge"], "123456"), "wrong 2FA code refused")
import time
nxt = pyotp.TOTP(begin["secret"]).at(time.time() + 30)
s2 = A.login_2fa(db, r["challenge"], nxt)
check(s2["status"] == "ok", "right code (next step, inside the window) signs in")
r = A.login(db, "new@example.com", "third-pass-word-3")
check(raises("BAD_CODE", A.login_2fa, db, r["challenge"], nxt), "the same code cannot be used twice")
rc = codes[0]
r = A.login(db, "new@example.com", "third-pass-word-3")
check(A.login_2fa(db, r["challenge"], rc)["status"] == "ok", "recovery code works")
r = A.login(db, "new@example.com", "third-pass-word-3")
check(raises("BAD_CODE", A.login_2fa, db, r["challenge"], rc), "recovery code works once only")
r = A.login(db, "new@example.com", "third-pass-word-3")
for _ in range(5):
    try: A.login_2fa(db, r["challenge"], "111111")
    except A.AuthError: pass
check(raises("CHALLENGE_EXPIRED", A.login_2fa, db, r["challenge"], pyotp.TOTP(begin["secret"]).now()), "five wrong codes kill the challenge")
check(raises("CHALLENGE_EXPIRED", A.login_2fa, db, "garbage", "123456"), "unknown challenge refused")

# ---- staff rules
os.environ["ADMIN_EMAIL"] = "boss@example.com"; os.environ["ADMIN_INITIAL_PASSWORD"] = "boss-pass-12345"
check(A.bootstrap_owner(db) and not A.bootstrap_owner(db), "owner is created once from the environment")
r = A.login(db, "boss@example.com", "boss-pass-12345")
check(r["scope"] == "enroll_2fa", "staff without 2FA get an enrolment-only session")
boss = db.users.find_one({"email": "boss@example.com"})
bs = A.twofa_begin(db, boss["id"]); A.twofa_confirm(db, boss["id"], pyotp.TOTP(bs["secret"]).now())
check(A.load_session(db, r["token"])[1]["scope"] == "full", "finishing enrolment upgrades the session")
check(raises("REQUIRED_FOR_STAFF", A.twofa_disable, db, boss["id"], "boss-pass-12345", "x"), "staff cannot turn 2FA off")
sess_doc = db.sessions.find_one({"_id": A.sha(r["token"])})
db.sessions.update_one({"_id": sess_doc["_id"]}, {"$set": {"last_seen": A.utcnow() - timedelta(minutes=30)}})
check(A.load_session(db, r["token"]) == (None, None), "staff session ends after the idle time")
r = A.login(db, "boss@example.com", "boss-pass-12345")
check(r["status"] == "needs_2fa", "staff sign-in asks for the code")
check(raises("BAD_ROLE", A.invite_staff, db, "x@example.com", "owner", "boss"), "cannot invite a second owner")
st, itok = A.invite_staff(db, "Help@Example.com", "support", "boss")
check(st["role"] == "support" and itok, "staff invited with a first-password link")
A.confirm_reset(db, itok, "support-first-pass-1")
check(A.can(st | {"role": "support"}, "users.read") and not A.can({"role": "support"}, "plans.write") and A.can(boss, "keys.write") and not A.can({"role": "admin"}, "keys.write"), "role permissions: support reads, admin cannot touch keys, owner can")
check(not A.can({"role": "analyst"}, "users.pii") and A.can({"role": "analyst"}, "analytics.read"), "analyst sees analytics but not personal data")
check(raises("LAST_OWNER", A.set_role, db, boss["id"], "admin", "x"), "last owner cannot be demoted")
check(raises("LAST_OWNER", A.set_disabled, db, boss["id"], True, "x"), "last owner cannot be turned off")
check(raises("LAST_OWNER", A.delete_account, db, boss["id"], "boss-pass-12345"), "last owner cannot be deleted")

# ---- disable, export, delete
tk = A.login(db, "help@example.com", "support-first-pass-1")
check(tk["status"] == "needs_2fa" or tk["scope"] == "enroll_2fa", "new staff must enrol in 2FA")
db.follows.insert_one({"user_id": u["id"], "kind": "team", "ref_iid": 1}); db.payments.insert_one({"_id": "in_1", "user_id": u["id"], "amount_paid": 999})
ex = A.export_account(db, u["id"])
check(ex["follows"] and ex["payments"] and "password_hash" not in str(ex["profile"]) and "secret_enc" not in str(ex["profile"]), "export holds the person's data, no secrets")
A.set_disabled(db, u["id"], True, "boss")
check(raises("ACCOUNT_DISABLED", A.login, db, "new@example.com", "third-pass-word-3"), "disabled account cannot sign in")
A.set_disabled(db, u["id"], False, "boss")
check(raises("BAD_CREDENTIALS", A.delete_account, db, u["id"], "wrong"), "delete needs the password")
info = A.delete_account(db, u["id"], "third-pass-word-3")
du = db.users.find_one({"id": u["id"]})
check(du["email"].startswith("deleted+") and "password_hash" not in du and not db.follows.count_documents({"user_id": u["id"]}), "delete removes personal data")
check(db.payments.find_one({"_id": "in_1"})["user_id"] is None, "payment rows stay but lose the link to the person")

# ---- rate limiter
now = A.utcnow()
res = [RL.hit(db, "k", 3, 60, now)[0] for _ in range(5)]
check(res == [True, True, True, False, False], "limiter allows 3 then refuses")
check(RL.hit(db, "k", 3, 60, now + timedelta(seconds=61))[0], "new window, allowed again")
check(RL.hit(db, "other", 3, 60, now)[0], "keys are independent")
print("\nALL ACCOUNT CHECKS PASSED")
