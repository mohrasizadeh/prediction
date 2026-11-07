// The 3-step welcome after sign-up (docs/24 §14): pick leagues, follow teams, choose e-mails. Every step can be skipped.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { del, patch, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import Icon from "../components/Icon";
import { Crest, LeagueMark } from "../components/Media";
import { Switch, useToast } from "../components/Ui";
import { useTitle } from "../components/Football";
import { ChipsRow, EmptyState, ErrorState, ProLock, Skeleton } from "../components/ui";

function Leagues({ all, picked, setPicked }) {
  const tap = (id) => setPicked(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]);
  return (
    <ul className="wl-leagues" data-testid="welcome-leagues">{all.map((l) => (
      <li key={l.id}><button type="button" className={`wl-lg${picked.includes(l.id) ? " on" : ""}`} aria-pressed={picked.includes(l.id)} onClick={() => tap(l.id)} data-testid={`welcome-league-${l.id}`}>
        <LeagueMark league={l} size={32} /><b>{l.name}</b><span className="wl-check">{picked.includes(l.id) && <Icon name="check" size={14} />}</span></button></li>
    ))}</ul>
  );
}

function Teams({ leagues, follows, setFollows }) {
  const [lg, setLg] = useState(leagues[0]?.id);
  const q = useApi(lg ? `/leagues/${lg}` : null);
  const toast = useToast();
  const teams = useMemo(() => [...new Map([...(q.data?.next || []), ...(q.data?.recent || [])].flatMap((m) => [m.home, m.away]).filter(Boolean).map((t) => [t.id, t])).values()]
    .sort((a, b) => a.name.localeCompare(b.name)), [q.data]);
  const tap = async (t) => {
    const on = follows.includes(t.id);
    try {
      if (on) await del("/me/follows", { kind: "team", ref_id: t.id }); else await put("/me/follows", { kind: "team", ref_id: t.id });
      setFollows(on ? follows.filter((x) => x !== t.id) : [...follows, t.id]);
    } catch (x) { toast(x.message || "Could not follow", "err"); }
  };
  return (
    <>
      {leagues.length > 1 && <ChipsRow label="League" value={lg} onChange={setLg} testid="welcome-team-league" options={leagues.map((l) => ({ id: l.id, label: l.name }))} />}
      {q.loading && !q.data ? <Skeleton shape="card" count={3} testid="welcome-teams-loading" /> : q.error ? <ErrorState message="We could not load the clubs." onRetry={q.reload} testid="welcome-teams-error" />
        : !teams.length ? <EmptyState icon="users" title="No clubs listed yet" testid="welcome-teams-empty">Try another league.</EmptyState> : (
          <ul className="wl-teams" data-testid="welcome-teams">{teams.map((t) => {
            const on = follows.includes(t.id);
            return <li key={t.id}><button type="button" className={`wl-team${on ? " on" : ""}`} aria-pressed={on} onClick={() => tap(t)} data-testid={`welcome-team-${t.id}`}><Crest team={t} size={44} /><b>{t.name}</b><small>{on ? <><Icon name="check" size={12} /> Following</> : "Follow"}</small></button></li>;
          })}</ul>
        )}
      <p className="wl-count" data-testid="welcome-picked">{follows.length} picked</p>
    </>
  );
}

const STEPS = [["Which leagues do you watch?", "We put them first in Explore."], ["Pick 3 teams to follow", "Their matches and players fill your feed."], ["What should we tell you?", "No more than you ask for."]];

export default function Welcome() {
  const { user, entitlements, setUser } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const lg = useApi("/leagues");
  const all = useMemo(() => (lg.data?.countries || []).flatMap((c) => c.leagues), [lg.data]);
  const [step, setStep] = useState(0);
  const [picked, setPicked] = useState(user?.prefs?.leagues || []);
  const [follows, setFollows] = useState([]);
  const [alerts, setAlerts] = useState(!!entitlements.alerts);
  const [lineups, setLineups] = useState(true);
  const [goals, setGoals] = useState(true);
  const [weekly, setWeekly] = useState(false);
  const [busy, setBusy] = useState(false);
  const saved = user?.prefs?.leagues;
  useEffect(() => { if (saved?.length) setPicked(saved); }, [saved]);
  useEffect(() => { setAlerts(!!entitlements.alerts); }, [entitlements.alerts]);
  useTitle("Welcome");
  const finish = async (save) => {
    setBusy(true);
    try {
      const r = await patch("/account/profile", { prefs: { welcomed: true, leagues: picked, ...(save && entitlements.alerts ? { alert_emails: alerts, alert_lineups: lineups, alert_goals: goals } : {}) } });
      setUser(r.user);
      if (save && weekly) await post("/newsletter/subscribe", { email: user.email, consent: true }).then(() => toast("Check your inbox to confirm the weekly e-mail")).catch(() => {});
      nav("/", { replace: true });   // was /following, which for a reader who skipped a step is an empty page telling them to sign up
    } catch (x) { toast(x.message || "Could not save", "err"); setBusy(false); }
  };
  const next = () => (step < 2 ? setStep(step + 1) : finish(true));
  const skip = () => (step < 2 ? setStep(step + 1) : finish(false));
  const teamLeagues = picked.length ? all.filter((l) => picked.includes(l.id)) : all;
  return (
    <section className="wl card" data-testid="welcome-page">
      <div className="wl-bar" aria-hidden="true">{STEPS.map((_, i) => <i key={i} className={i <= step ? "on" : ""} />)}</div>
      <small className="k-sec" data-testid="welcome-step">Step {step + 1} of 3</small>
      <h1>{STEPS[step][0]}</h1><p className="k-faint">{STEPS[step][1]}</p>
      <div className="wl-body">
        {lg.loading && !lg.data ? <Skeleton shape="row" count={4} testid="welcome-loading" /> : lg.error ? <ErrorState message="We could not load the leagues." onRetry={lg.reload} testid="welcome-error" />
          : step === 0 ? <Leagues all={all} picked={picked} setPicked={setPicked} />
          : step === 1 ? <Teams leagues={teamLeagues} follows={follows} setFollows={setFollows} />
          : (
            <div className="switch-list card" data-testid="welcome-alerts">
              <Switch label="Alerts for my teams and players" hint={entitlements.alerts ? "By e-mail. Pick which below." : "Part of Pro"} checked={alerts && !!entitlements.alerts} disabled={!entitlements.alerts} onChange={setAlerts} testid="welcome-alert-emails" />
              {entitlements.alerts && alerts && <>
                <Switch label="Lineups for my teams" hint="When the starting elevens are confirmed" checked={lineups} onChange={setLineups} testid="welcome-alert-lineups" />
                <Switch label="Goals and red cards" hint="During matches you follow" checked={goals} onChange={setGoals} testid="welcome-alert-goals" />
              </>}
              {!entitlements.alerts && <div className="wl-pro"><ProLock testid="welcome-alerts-pro" /></div>}
              <Switch label="Weekly e-mail" hint="The week's strongest reads. We send a link to confirm." checked={weekly} onChange={setWeekly} testid="welcome-weekly" />
              <p className="k-faint k-small">Change these any time in Account.</p>
            </div>
          )}
      </div>
      <div className="wl-foot">
        <button type="button" className="btn btn--primary btn--lg btn--block" disabled={busy} onClick={next} data-testid="welcome-next">{step < 2 ? "Next" : busy ? "Starting…" : "Start"}</button>
        <button type="button" className="k-link" disabled={busy} onClick={skip} data-testid="welcome-skip">Skip</button>
      </div>
    </section>
  );
}
