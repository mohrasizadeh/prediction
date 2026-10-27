# Sign in an iteration-12 TEST staff user (2FA handled by admin_login_helper) and print the session cookie value
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import admin_login_helper as H


def session_for(role):
    H.CREDS = {"email": f"delivered+t12{role}@resend.dev", "password": "Test-Admin-Pass-2026!q"}
    H.STATE = f"/tmp/t12_{role}_totp.json"
    return H.admin_session()


if __name__ == "__main__":
    out = {}
    for role in sys.argv[1:]:
        s = session_for(role)
        out[role] = s.cookies.get_dict()
    json.dump(out, open("/tmp/t12_cookies.json", "w"))
    print({k: list(v.keys()) for k, v in out.items()})
