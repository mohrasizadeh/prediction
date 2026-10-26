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

  const refresh = useCallback(async (tries = 0) => {
    try {
      const m = await get("/auth/me");
      setMe(m);
      setLoading(false);
      return m;
    } catch (err) {
      // Only a real 401 means signed out; a 429 or a network blip keeps who we had.
      if (err?.status === 401) {
        setMe({ user: null });
        setLoading(false);
        return { user: null };
      }
      let kept = null;
      setMe((m) => { kept = m; return m; });
      // Fresh page load hit the rate limit: we do not know who this is yet, so ask again shortly.
      if (!kept && err?.status === 429 && tries < 5) {
        await new Promise((r) => setTimeout(r, 2500));
        return refresh(tries + 1);
      }
      setMe((m) => m || { user: null });
      setLoading(false);
      return kept || { user: null };
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

  // After a PATCH that returns the user, merge it instead of calling /auth/me again (it is rate limited).
  const setUser = useCallback((u) => setMe((m) => ({ ...(m || {}), user: { ...(m?.user || {}), ...u } })), []);
  const value = { me, user: me?.user || null, entitlements: me?.entitlements || {}, loading, refresh, signOut, setUser };
  return createElement(AuthCtx.Provider, { value }, children);
}

export const useAuth = () => useContext(AuthCtx);
