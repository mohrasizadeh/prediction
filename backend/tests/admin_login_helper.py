# Helper: sign in test admin (enrol TOTP on first sign-in), persist secret, return requests session with full scope
import json
import os
import time

import pyotp
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CREDS = {"email": "test_e1_admin@example.com", "password": "Test-Admin-Pass-2026!q"}
STATE = "/tmp/test_admin_totp.json"


def _load():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {}


def _code(secret, last=None):
    t = pyotp.TOTP(secret)
    c = t.now()
    while c == last:
        time.sleep(2)
        c = t.now()
    return c


def admin_session():
    st = _load()
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS)
    r.raise_for_status()
    d = r.json()
    if d.get("needs_2fa"):
        code = _code(st["secret"], st.get("last"))
        r = s.post(f"{BASE_URL}/api/auth/login/2fa", json={"challenge": d["challenge"], "code": code})
        st["last"] = code
        json.dump(st, open(STATE, "w"))
        r.raise_for_status()
        return s
    if d.get("scope") != "full":
        b = s.post(f"{BASE_URL}/api/account/2fa/begin").json()
        secret = b.get("secret") or b.get("key")
        if not secret and b.get("otpauth_uri"):
            secret = pyotp.parse_uri(b["otpauth_uri"]).secret
        code = _code(secret)
        c = s.post(f"{BASE_URL}/api/account/2fa/confirm", json={"code": code})
        c.raise_for_status()
        json.dump({"secret": secret, "last": code, "recovery": c.json()["recovery_codes"], "begin": b}, open(STATE, "w"))
        return admin_session()
    return s


if __name__ == "__main__":
    s = admin_session()
    print(s.get(f"{BASE_URL}/api/auth/me").json().get("scope"), s.cookies.get_dict().keys())
