// Who is signed in, their plan and entitlements (docs/13 section 3).
// GET /api/auth/me never fails for signed-out visitors. The UI uses entitlements only as a hint; the server enforces.
import { createContext, createElement, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { get, onApiError, post } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  const refresh = useCallback(async () => {
    try {
      const m = await get("/auth/me");
      setMe(m);
      return m;
    } catch {
      setMe({ user: null });
      return { user: null };
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(
    () =>
      onApiError((err) => {
        if (err.code === "SIGN_IN_REQUIRED") {
          setMe((m) => ({ ...(m || {}), user: null }));
          navigate(`/sign-in?next=${encodeURIComponent(location.pathname + location.search)}`);
        } else if (err.code === "ENROLL_2FA_REQUIRED") {
          navigate("/enroll-2fa");
        }
      }),
    [navigate, location]
  );

  const signOut = useCallback(async () => {
    await post("/auth/logout").catch(() => {});
    await refresh();
    navigate("/");
  }, [refresh, navigate]);

  const value = { me, user: me?.user || null, entitlements: me?.entitlements || {}, loading, refresh, signOut };
  return createElement(AuthCtx.Provider, { value }, children);
}

export const useAuth = () => useContext(AuthCtx);
