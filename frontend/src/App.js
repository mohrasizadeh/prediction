// Every screen in docs/01 section 5, docs/13 section 2 and the admin (docs/10, docs/17) has a route here.
// Phase 0: account screens, account area and the admin are real. Each <Spec> is a data screen for a later phase.
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import Layout from "./components/Layout";
import Spec from "./components/Spec";
import Today from "./pages/Today";
import MarkdownPage from "./pages/Markdown";
import Account from "./pages/Account";
import { ChangePasswordFirst, ConfirmEmail, Enroll2FA, ForgotPassword, ResetPassword, SignIn, SignUp, VerifyEmail } from "./pages/Auth";
import AdminApp from "./admin/AdminApp";
import { useAuth } from "./lib/auth";
import { resolveMode, useSite } from "./lib/site";
import { Loading } from "./components/States";

const P = (props) => <Spec {...props} />;

function WithId({ make }) {
  const { id } = useParams();
  return make(id);
}

export function NotFound() {
  return <div className="state state-404" data-testid="not-found"><p className="big-404">404</p><p>We could not find that page.</p></div>;
}

// Staff without 2FA may only enrol; a first password must be replaced before anything else.
function Gates() {
  const { me } = useAuth();
  const { pathname } = useLocation();
  const nav = useNavigate();
  useEffect(() => {
    if (!me?.user) return;
    if (me.scope === "enroll_2fa" && pathname !== "/enroll-2fa") nav("/enroll-2fa", { replace: true });
    else if (me.scope !== "enroll_2fa" && me.user.must_change_password && !["/change-password", "/enroll-2fa"].includes(pathname)) nav("/change-password", { replace: true });
  }, [me, pathname, nav]);
  return null;
}

// Theme: the person's saved choice, else this browser's choice, else default_mode, else the system setting.
function ThemeSync() {
  const { cfg, pref } = useSite();
  const { user } = useAuth();
  useEffect(() => {
    const saved = user?.theme && user.theme !== "system" ? user.theme : pref;
    const apply = () => { document.documentElement.dataset.theme = resolveMode(saved, cfg); };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, [cfg, pref, user]);
  return null;
}

function AdminGate() {
  const { user, me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user || user.role === "user") return <Layout><NotFound /></Layout>;
  if (me?.scope === "enroll_2fa") return <Navigate to="/enroll-2fa" replace />;
  return <AdminApp />;
}

export default function App() {
  const { ready } = useSite();
  if (!ready) return <div className="boot" data-testid="app-boot"><span className="brand-mark" /></div>;
  return (
    <>
      <Gates />
      <ThemeSync />
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Today />} />
          <Route path="match/:id" element={<WithId make={(id) => <P title="Match" docs="docs/01 §5 screen 2, docs/18 (rotation chip), docs/19 (crests)" routes={[`GET /api/matches/${id}`]} probe={`/matches/${id}`} />} />} />
          <Route path="insights" element={<P title="Insights" docs="docs/01 §5 screen 3, docs/04 ForecastCard" routes={["GET /api/insights"]} probe="/insights" query={{ limit: 20 }} />} />
          <Route path="finder" element={<P title="Forecast Finder" docs="docs/01 §5 screen 4, docs/02, docs/06 §2 and §4 (plan limits)" routes={["GET /api/finder"]} />} />
          <Route path="leagues" element={<P title="Leagues" docs="docs/01 §5 screen 5" routes={["GET /api/leagues"]} probe="/leagues" />} />
          <Route path="teams" element={<P title="Teams" docs="docs/01 §5 screen 5" routes={["GET /api/leagues"]} probe="/leagues" />} />
          <Route path="league/:id" element={<WithId make={(id) => <P title="League" docs="docs/01 §5 screen 6" routes={[`GET /api/leagues/${id}`, "…/fixtures", "…/leaderboard", "…/referees"]} probe={`/leagues/${id}`} />} />} />
          <Route path="team/:id" element={<WithId make={(id) => <P title="Team" docs="docs/01 §5 screen 7, docs/02 (squad grid)" routes={[`GET /api/teams/${id}`, "…/squad-grid", "…/totals", "…/against"]} probe={`/teams/${id}`} />} />} />
          <Route path="player/:id" element={<WithId make={(id) => <P title="Player" docs="docs/01 §5 screen 8" routes={[`GET /api/players/${id}`, "…/history", "PUT /api/me/follows", "PUT /api/me/notes/{id}"]} probe={`/players/${id}`} />} />} />
          <Route path="following" element={<P title="Following" docs="docs/01 §5 screen 10" routes={["GET /api/me/follows", "GET /api/me/following-feed", "GET /api/me/saved"]} probe="/me/following-feed" />} />
          <Route path="track-record" element={<P title="Track record" docs="docs/01 §5 screen 11" routes={["GET /api/track-record"]} probe="/track-record" />} />
          <Route path="search" element={<P title="Search" docs="docs/01 §5 screen 13 (overlay, 200 ms debounce)" routes={["GET /api/search?q="]} />} />
          <Route path="pricing" element={<P title="Pricing" docs="docs/13 §2, docs/14" routes={["GET /api/plans", "POST /api/billing/checkout"]} probe="/plans" />} />
          <Route path="account/*" element={<Account />} />
          <Route path="contact" element={<P title="Contact" docs="docs/13 §2" routes={["POST /api/contact"]} />} />
          <Route path="unsubscribe" element={<P title="Unsubscribe" docs="docs/13 §2, docs/14" routes={["GET /api/email/unsubscribe?t=", "POST /api/email/unsubscribe"]} />} />
          <Route path="learn" element={<MarkdownPage slug="learn" />} />
          <Route path="learn/:slug" element={<MarkdownPage />} />
          <Route path="legal/:slug" element={<MarkdownPage />} />
          <Route path="sign-in" element={<SignIn />} />
          <Route path="sign-in/2fa" element={<Navigate to="/sign-in" replace />} />
          <Route path="sign-up" element={<SignUp />} />
          <Route path="signup" element={<Navigate to="/sign-up" replace />} />
          <Route path="terms" element={<Navigate to="/legal/terms" replace />} />
          <Route path="privacy" element={<Navigate to="/legal/privacy" replace />} />
          <Route path="about" element={<Navigate to="/legal/about" replace />} />
          <Route path="verify-email" element={<VerifyEmail />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="reset-password" element={<ResetPassword />} />
          <Route path="confirm-email" element={<ConfirmEmail />} />
          <Route path="enroll-2fa" element={<Enroll2FA />} />
          <Route path="change-password" element={<ChangePasswordFirst />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="admin/*" element={<AdminGate />} />
      </Routes>
    </>
  );
}
