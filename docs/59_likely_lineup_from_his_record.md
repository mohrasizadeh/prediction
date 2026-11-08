# 59 — "Likely lineup" is read off his record of starting

Supersedes the `likely` / `unsure` rows of the badge table in
`27_if_he_plays_and_lineup_badge.md` §2. Everything else in
docs/27 stands: the percentage is still "if he plays", the four badge values are unchanged, and
`engine.min_p_play` still decides on the chance to play whether a card exists at all.

docs/58 took every lineup condition out of the tier and said, in its last line, that the
uncertainty "moved to the badge that exists to carry it". It did. This is about what it found when
it got there.

## What was wrong

The badge was `p_play >= engine.likely_starter_p`, with the setting at **0.85**. `p_play` comes
from the absence model, whose one continuous input is `ps`, a recency-weighted start rate with a
Laplace prior:

    ps = (Σ w·started + 1) / (Σ w + 2),   w = 0.5 ^ (games ago / 12)

The half-life is 12 games, so `Σ w` converges to **17.83** however long the history is. A player
who has started **every single game** therefore tops out at

    ps ≤ 18.83 / 19.83 = 0.9496

and `ABSENCE_START = (-0.107, 0.719, …)` turns that ceiling into

    z = -0.107 + 0.719 · logit(0.9496) = 2.004   →   p_play ≤ 0.8812

So the gate sat at **96% of the achievable maximum**. Working backwards, 0.85 asks for
`ps ≥ 0.9286`, which is having started about **97.6% of recent games** — a standard no real
footballer meets for long, because one rested weekend breaks it.

Measured on the demo league 48 hours out, with the shipped defaults:

| | |
|---|---|
| player cards | 85 |
| badged `unsure` | **43 (51%)** |
| observed `p_play` | 0.52 – 0.85, median 0.85 |

Of the 43 doubts, **8 were players who had started NINE of their club's last ten matches** and
**3 had started all ten**. They sat on a `p_play` of 0.84 against a gate of 0.85, on a scale whose
maximum is 0.88. The product's one remaining answer to "will he start" was a coin-flip decided in
a window 0.03 wide, and the badge said "Lineup not sure" about the most nailed-on starters in the
league.

## The rule now

> "Look at the past 10 matches of the player — if he played as starter for most of them … then
> they deserve to be likely lineup." — the owner

**Of his club's last `engine.starter_record_n` (10) matches, did he start at least
`engine.starter_start_share` (0.6) of them?**

- **His CLUB's matches, not his own appearances.** The two are different and only the first
  answers the question. A player who missed five of the club's last ten and started the five he
  played started 100% of his appearances and half of his club's games. Measured: the appearance
  share passes 84 of 85 cards at a 0.5 threshold and 81 at 0.6 — it cannot tell a regular from a
  stand-in, because the games that would have told them apart are the ones it leaves out.
- **0.6, because "likely" is a more-likely-than-not call.** The honest floor is 0.5; six of the
  last ten clears it with a margin. The two differ by one card on the demo league, and every
  player left at "Lineup not sure" by 0.6 had started five or fewer of his club's last ten.
- **The window starts at his first appearance for the club.** A signing has no record of the
  matches played before he arrived, and charging him for them would read a player who joined four
  matches ago and started all four as 4 of 10 — a doubt for his first two months. Trimming changes
  nothing for a player who has been there all along, which is almost everyone, so absences still
  count against him. Fewer than half the window since he arrived and there is no record to read
  (see below).
- **A run of recent absences overrides the record** (`engine.starter_max_missed`, 1). One missed
  match is ordinary rotation; two or more in a row is what an injury or a suspension looks like in
  the data before anyone tells us. It is the same count the absence model reads (docs/22).
- **A stated doubt overrides the record.** A player the feed or the admin marks Doubtful is
  "Lineup not sure" whatever he has started.
- `engine.starter_from_record` switches the whole thing off and restores the old gate exactly.

### Minutes were measured and left out

The owner also floated "an average minutes a starter plays in the past 10 matches". Measured on
the demo league it does not discriminate: mean minutes **in matches he started** runs 73–86 for
every player on the board, fringe players included, so the number is the same for a regular and
for a stand-in who starts twice a month. Mean minutes over the club's last ten *does* track the
start share closely (a 45-minute floor and a 0.6 start share pick out sets one card apart) — but
it conflates two things the badge must keep apart: a substitute who plays 45 minutes every week
averages 45 and starts nothing.

And `provider.pitchapi.player_keys.minutes.key` **ships as null**. Keying the badge on a column
that can be unmapped is how this product has already lost its forwards once
(`normalize.ZERO_WHEN_ABSENT`) and every player row in a league once (`engine_bridge.build_frames`
§"WHO ACTUALLY PLAYED"). Starts carry the signal; minutes carry the risk.

### A record we cannot read is never an answer

`started` comes from the lineups endpoint (`normalize.normalize_match`:
`p["started"] = p["ext_id"] in started`), so a league without that coverage reports eleven
substitutes a side — the same shape of bug as the unmapped minutes key, one column over. The
engine therefore refuses to produce a record at all when:

- the club has fewer than half the window of matches on record (early season), or
- he has fewer than half the window of club matches since his first appearance for them (a very
  recent arrival), or
- the window's rows average fewer than `MIN_STARTERS_SEEN` (7) starters per club match. A real
  eleven gives 10 or 11, goalkeepers usually being excluded by `engine.exclude_positions`.

`starts_recent` is then `None`, and `None` means **fall back to the old chance-to-play gate** —
never `unsure`. A missing column must not quietly call every player in a league a doubt.

## What is not changed

The badge is a display signal, and this changes the badge only. Verified by running the demo
league with the setting off and on and comparing every stored row:

- **the tier** — graded on `p` alone since docs/58, and `tiering.assign` does not read the badge;
- **`engine.min_p_play` (0.5) and `engine.min_p_start`** — which cards exist at all is a relevance
  decision and it stays on `p_play` / `p_start`;
- **the record anchor** (docs/32), which moves the percentage;
- **`tier_basis`**, and the legacy non-earned tier's `solid_ok`;
- **`p`, `lo`, `hi`, `p_play`** — identical to the last bit.

`confirmed` and `bench` come from a published eleven and are untouched. Each forecast now stores
`starts_recent` and `club_recent`, so the badge can be checked against the ten-game strip drawn
directly under it.

## What a reader sees change

| demo league, 48h out | before | after |
|---|---|---|
| player cards badged `likely` | 42 | **77** |
| player cards badged `unsure` | 43 | **8** |
| published player lines `likely` / `unsure` | 74 / 65 | **130 / 9** |
| tiers | 26 Solid, 59 Watch | unchanged |

Nobody is demoted. The eight players still reading "Lineup not sure" had started 2, 3, 4, 4, 4, 4,
4 and 5 of their club's last ten — which is what the badge is for.
