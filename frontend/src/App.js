// Every screen in docs/01 section 5, docs/13 section 2 and the admin (docs/10, docs/17) has a route here.
// Public site routes, account area and the admin.
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import Layout from "./components/Layout";
import Today from "./pages/Today";
import Match from "./pages/Match";
import League, { Leagues } from "./pages/League";
import Team from "./pages/Team";
import Player from "./pages/Player";
import Referee from "./pages/Referee";
import Referees from "./pages/Referees";
import Live from "./pages/Live";
import DevKit from "./pages/DevKit";
import Pricing from "./pages/Pricing";
import Finder from "./pages/Finder";
import { Insights, TrackRecord } from "./pages/Insights";
import { Following, Search } from "./pages/Following";
import MarkdownPage from "./pages/Markdown";
import Account from "./pages/Account";
import { ChangePasswordFirst, ConfirmEmail, Enroll2FA, ForgotPassword, ResetPassword, SignIn, SignUp, VerifyEmail } from "./pages/Auth";
import AdminApp from "./admin/AdminApp";
import { useAuth } from "./lib/auth";
import { resolveMode, useSite } from "./lib/site";
import { Loading } from "./components/States";
import Contact from "./pages/Contact";
import { NewsletterConfirm, Unsubscribe } from "./pages/EmailLinks";


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
          <Route path="match/:id" element={<Match />} />
          <Route path="live" element={<Live />} />
          <Route path="dev/kit" element={<DevKit />} />
          <Route path="insights" element={<Insights />} />
          <Route path="finder" element={<Finder />} />
          <Route path="leagues" element={<Leagues />} />
          <Route path="teams" element={<Leagues />} />
          <Route path="league/:id" element={<League />} />
          <Route path="team/:id" element={<Team />} />
          <Route path="player/:id" element={<Player />} />
          <Route path="referee/:name" element={<Referee />} />
          <Route path="referees" element={<Referees />} />
          <Route path="following" element={<Following />} />
          <Route path="track-record" element={<TrackRecord />} />
          <Route path="search" element={<Search />} />
          <Route path="pricing" element={<Pricing />} />
          <Route path="account/*" element={<Account />} />
          <Route path="contact" element={<Contact />} />
          <Route path="unsubscribe" element={<Unsubscribe />} />
          <Route path="newsletter/confirm" element={<NewsletterConfirm />} />
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
