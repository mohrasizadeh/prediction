"""selftest_waitlist_mail.py -- the e-mail sequence the waitlist page promises (docs/69).

Proves the promises, not the plumbing:

  * "three strong reads every match day" means THREE and means MATCH DAY: a day with fewer than
    three forecasts above the floor sends nothing rather than an e-mail apologising for itself,
    and "today" ends at local midnight, so a kick-off tomorrow morning is never listed under
    today's date;
  * it reaches the people who signed up on /waitlist and nobody else -- a footer subscriber asked
    for a different thing and must not receive this;
  * the header graphic is the card about a player the e-mail actually names, taken from the PNG the
    ad builder already rendered and published, and a day with no batch still sends;
  * the three forecasts arrive as a table rather than as visible angle brackets, while a player
    name out of the data feed is still escaped;
  * once a day: a second run the same day sends nothing, whoever starts it;
  * no banned word reaches an inbox, including from a market label this app did not author;
  * the record line is absent until there is a record, and is never phrased as a score.
"""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import mongomock
import emailer as E, mongo_init, newsletter as N, settings_store as S, social as SOC
import waitlist_mail as WL


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


class Fake:
    """Stands in for the provider. Keeps every message, so the test can read what was sent."""
    def __init__(self):
        self.out = []

    def send(self, payload, idem=None):
        self.out.append(payload)
        return {"id": f"fake-{len(self.out)}"}


os.environ["PUBLIC_BASE_URL"] = "https://example.test"
db = mongomock.MongoClient()["wl"]; mongo_init.ensure_indexes(db)
S.put(db, "email.enabled", True)
S.put(db, "email.marketing_enabled", True)
S.put(db, "email.from_address", "hello@example.test")
S.put(db, "email.footer_address", "1 Example St, Toronto")
S.put(db, "waitlist.email_enabled", True)
S.put(db, "waitlist.email_hour", 9)

now = dt.datetime(2026, 11, 14, 11, 0, tzinfo=dt.timezone.utc)

# ---------------------------------------------------------------- fixtures
for i in (1, 2, 3, 4):
    db.teams.insert_one({"iid": i, "id": f"t{i}", "ext_id": f"T{i}", "name": f"Club {i}"})
# A club name with a character that has to be escaped, because club names come from the feed.
db.teams.update_one({"iid": 2}, {"$set": {"name": 'Club "Two" & Co'}})
for i in (101, 102, 103, 104):
    db.players.insert_one({"iid": i, "id": f"p{i}", "ext_id": f"P{i}", "name": f"Player {i}"})
db.leagues.insert_one({"iid": 10, "id": "l10", "ext_id": "L10", "name": "Example League"})
for i in (1, 2):
    db.matches.insert_one({"iid": 500 + i, "id": f"m{i}", "ext_id": f"M{i}", "home_iid": 1, "away_iid": 2,
                           "kickoff": now + dt.timedelta(hours=6)})


def forecast(i, *, p, player, market="2+ shots", hours=6, stat="shots"):
    db.forecasts.insert_one({"id": f"f{i}", "fkey": f"k{i}", "match_iid": 501, "league_iid": 10,
                             "scope": "player", "team_iid": 1, "opp_iid": 2, "player_iid": player,
                             "stat": stat, "thr": 1.5, "market": market, "p": p, "tier": "Strong",
                             "kickoff": now + dt.timedelta(hours=hours), "is_current": True,
                             "hidden": False, "usual": 2.1, "ladder": {"1.5": p}})


# ---------------------------------------------------------------- 1. not a match day
forecast(1, p=0.94, player=101)
forecast(2, p=0.91, player=102)
check(not WL.is_match_day(db, now), "two forecasts is not a match day -- the promise is three")
out = WL.send_matchday(db, now=now, client=Fake())
check(out["sent"] == 0 and "only 2" in out["skipped"],
      f"so nothing is sent, and the reason says how many it found (said: {out.get('skipped')})")

# ---------------------------------------------------------------- 2. a match day, and who gets it
forecast(3, p=0.88, player=103)
forecast(4, p=0.86, player=104, hours=200)          # outside the window: too far away to be today's
check(WL.is_match_day(db, now), "a third forecast above the floor makes it a match day")
rows = WL.strongest(db, now=now)
check([f["fkey"] for f in rows] == ["k1", "k2", "k3"], "the three are the likeliest, in order")
check(all(f["fkey"] != "k4" for f in rows), "a match six days out is not part of today's three")

# The window ends with the LOCAL DAY. A flat look-ahead in hours put a 09:00 kick-off that was on
# the Sunday into an e-mail headed "Saturday 14 November" -- a time with the wrong day on it, which
# the reader has no way to spot. This is the regression that proves it cannot come back.
forecast(5, p=0.99, player=104, hours=22)           # 09:00 the next morning: likeliest, and not today
check(round(WL.window_h(db, now)) == 13, "the window runs to midnight local, not a fixed number of hours")
check([f["fkey"] for f in WL.strongest(db, now=now)] == ["k1", "k2", "k3"],
      "so tomorrow morning's match is left out even though it is the likeliest line on the board")
db.forecasts.delete_one({"fkey": "k5"})
# A send configured for late evening has almost no window left, and that is the correct answer:
# there is no football left today to write about.
check(WL.window_h(db, now.replace(hour=23)) <= 1, "a late send looks ahead barely an hour")
check(not WL.is_match_day(db, now.replace(hour=23)), "and therefore sends nothing rather than tomorrow's")

consent = S.get(db, "newsletter.consent_text")
S.put(db, "newsletter.double_optin", False)
N.subscribe(db, "reader@example.test", source="waitlist", consent_text=consent, consent=True, name="Sam")
N.subscribe(db, "footer@example.test", source="footer", consent_text=consent, consent=True)
check(WL.count(db) == 1, "only the /waitlist sign-up is on the waitlist")
check({m["email"] for m in WL.members(db)} == {"reader@example.test"},
      "members() excludes the footer subscriber, who asked for something else")
check(next(iter(WL.members(db)))["display_name"] == "Sam", "and carries the name they gave")
check("waitlist" in E.SEGMENTS, "a campaign can be aimed at the waitlist as its own segment")
check({u["email"] for u in E.segment_users(db, "waitlist")} == {"reader@example.test"},
      "and that segment resolves to the same people")

# the welcome went out on confirmation, once
welcome = list(db.email_log.find({"template": "waitlist_welcome"}))
check(len(welcome) == 1, "confirming a waitlist sign-up sends exactly one welcome")
check(welcome[0]["to"] == "reader@example.test", "to the person who signed up")
db.email_log.delete_many({})

# ---------------------------------------------------------------- 3. the header graphic
# Two posts queued for today: one about a player in the e-mail, one about anything else. The
# earlier one is NOT the one about a named player, so preferring it would be the wrong answer.
IMG_OTHER = "https://example.test/api/site/assets/other.png"
IMG_K2 = "https://example.test/api/site/assets/k2.png"
SOC.queue(db, "owner@example.test", platform="instagram", kind="post", media=[IMG_OTHER],
          caption="Example League tomorrow", scheduled_at=now.replace(hour=8), fkeys=["k99"])
SOC.queue(db, "owner@example.test", platform="instagram", kind="post", media=[IMG_K2],
          caption="Player 102 has reached 2+ shots in 9 of his last 10.",
          scheduled_at=now.replace(hour=13), fkeys=["k2"])
img = WL.header_image(db, rows, now)
check(img[0] == IMG_K2,
      "the graphic is the card about a player the e-mail names, not whatever was queued first")
# Most clients block remote images until asked, so the alt text is what is on screen when the
# e-mail opens. An empty one would leave a blank box at the top of every send.
check("Player 102" in img[1], f"and it carries that post's own caption as its alt text (said: {img[1]!r})")
check(WL.header_image(db, [{"fkey": "nope"}], now)[0] == IMG_OTHER,
      "with no match it falls back to another of today's cards rather than to nothing")
check(WL.header_image(db, rows, now + dt.timedelta(days=3)) is None,
      "and a day with no batch queued gets no graphic")
# "Today" for the graphic is the LOCAL day, not the UTC one: at an offset like -300 a post
# scheduled 02:00 UTC is 21:00 the previous evening where the owner is, and not today's card.
S.put(db, "waitlist.email_tz_offset_min", -300)
SOC.queue(db, "owner@example.test", platform="instagram", kind="post",
          media=["https://example.test/api/site/assets/yesterday.png"],
          caption="Last night", scheduled_at=now.replace(hour=2), fkeys=[])
check(WL.header_image(db, rows, now)[0] == IMG_K2,
      "a post at 02:00 UTC belongs to the previous local evening, not to today's e-mail")
S.put(db, "waitlist.email_tz_offset_min", 0)

# ---------------------------------------------------------------- 4. what lands in the inbox
fake = Fake()
out = WL.send_matchday(db, now=now, client=fake)
check(out["sent"] == 1 and out["with_image"], "one e-mail went out, with the graphic")
msg = fake.out[0]
check("14 November" in msg["subject"], f"the subject carries the date (said: {msg['subject']!r})")
html = msg["html"]
check(IMG_K2 in html, "the chosen card is the header image")
check('alt="' in html and "Player 102" in html.split('alt="')[1][:200],
      "and the image carries alt text, for the client that blocks it")
check('<table' in html and 'Player 101' in html, "the three arrive as a table, not as escaped markup")
check("&lt;table" not in html, "the block built by this module is not double-escaped")
check('Club &quot;Two&quot; &amp; Co' in html, "but a club name out of the data feed IS escaped")
check("94%" in html and "91%" in html and "88%" in html, "each one shows its likelihood")
check("Player 104" not in html, "and the match six days out is not in it")
check("unsubscribe" in html.lower(), "marketing mail carries the one-click unsubscribe")
check("1 Example St" in html, "and the postal address the law asks for")
check("Player 101" in msg["text"] and "2+ shots" in msg["text"], "the plain-text half is real, not empty")
check("<table" not in msg["text"], "and carries no markup")
import textguard as TG
check(TG.find([msg["subject"], msg["html"], msg["text"]]) == [],
      "nothing in the e-mail uses a word this product does not publish")

# ---------------------------------------------------------------- 5. once a day
check(not WL.due(db, now), "having sent today, the job is no longer due")
again = Fake()
out2 = WL.send_matchday(db, now=now + dt.timedelta(hours=2), client=again)
check(out2["sent"] == 0 and not again.out,
      "and a second run the same day sends nothing, including from the admin screen's Send now")
check(WL.due(db, now + dt.timedelta(days=1)), "tomorrow it is due again")
check(not WL.due(db, now.replace(hour=2)), "and before the chosen hour it is not")

# ---------------------------------------------------------------- 6. the record line
check("of the time" not in html,
      "with nothing scored yet, the e-mail makes no claim about how we have done")
for i in range(400):
    db.forecast_outcomes.insert_one({"forecast_id": f"h{i}", "p": 0.9, "thr": 1.5, "reached": i % 10 != 0,
                                     "player_played": True, "tier": "Strong", "stat": "shots",
                                     "scope": "player", "scored_at": now - dt.timedelta(days=2)})
rec = WL.body_html(db, rows, None)
check("of the time" in rec and "scored forecasts" in rec,
      "once there is a record it is stated, with the sample size")
check("90%" in rec, "as calibration: what we said, next to what happened")
check(TG.find([rec]) == [], "and the record line uses none of the banned words either")

# ---------------------------------------------------------------- 7. the switches
S.put(db, "waitlist.email_enabled", False)
check(WL.send_matchday(db, now=now + dt.timedelta(days=1), client=Fake())["sent"] == 0,
      "the setting switches the whole thing off")
S.put(db, "waitlist.email_enabled", True)
S.put(db, "email.footer_address", "")
o = WL.send_matchday(db, now=now + dt.timedelta(days=1), client=Fake())
check(o["sent"] == 0 and "postal address" in o["skipped"],
      "and marketing mail without a postal address refuses to go, naming what is missing")

print("selftest_waitlist_mail: all checks passed")
