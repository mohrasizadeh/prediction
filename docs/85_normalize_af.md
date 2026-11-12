# 85. normalize_af: their JSON, our dicts

The adapter. `normalize_af.normalize_match` returns exactly what `normalize.normalize_match`
returns, so `ingest.py` changes only in which client it calls and which endpoint it reads, and
nothing downstream — the frames, the engine, the cards — learns that the provider changed.

Input is one element of `/fixtures?ids=` (docs/81 §1): the fixture, its teams, its score, its
events, its lineups, its team statistics and its player statistics, in one answer.

## The column map

| our column | theirs | |
|---|---|---|
| minutes | `games.minutes` | |
| shots / sot | `shots.total` / `shots.on` | |
| goals / assists | `goals.total` / `goals.assists` | |
| saves | `goals.saves` | |
| tackles / interceptions | `tackles.total` / `tackles.interceptions` | |
| fouls_committed / fouls_won | `fouls.committed` / `fouls.drawn` | |
| passes | `passes.total` | |
| **xg** | — | needs an add-on; `engine.xg_blend` is 0 |
| **clearances** | — | not carried, and used by no market |

Team statistics are read by **display string** through `provider.apifootball.team_keys`, because
that is how this provider identifies a statistic. `tackles` is deliberately unmapped: there is no
team tackles statistic, and the team total is the sum of the players', which is the fallback
`normalize.py` has always had.

Three things that come free here and cost a call each on PitchAPI: the **referee** (on the fixture,
so `referees.py` is fed without `ingest.match_extra_detail`), the **coach**, and the **started
flag** (`games.substitute`, where the old code had to cross-reference the lineup).

## Three decisions, not transcription

**1. Absent-or-zero, rebuilt.** The provider omits a count that is zero and says absence is
inconclusive. That ambiguity is the bug that deleted appearances, read a deleted appearance as an
absence, halved `p_play` and dropped every card of the players it hit — position-correlated, because
a forward is who records no tackle (568 stored rows fell to 395).

PitchAPI's guard asked whether the stat's *group* was present on that player. There are no groups
here, and the replacement tests the actual question: **is this field non-null for any other player
in the same fixture?** Fifteen other players with a tackle count means the match tracked tackles, so
a null here is a real zero. Nobody with one means it was not tracked, and it stays `None`.

It looks across the whole fixture, both teams, because tracking is a property of the match.

**2. Keepers keep their tackles.** `normalize.players` blanks a goalkeeper's tackles, because
PitchAPI sent keepers no defence group at all. Here every player's tackles are in the same object,
so a keeper's 0 is real — and reproducing the blanking would put `None` in a column that is in
`engine_bridge.PLAYER_REQUIRED`, which is what deletes keeper rows on a flat dropna (docs/70). The
old behaviour was a provider artefact, not a rule, and carrying it over would cost the saves market.

**3. Extra time is flagged and excluded from the fitting frame.** `statistics` covers the whole
match including extra time, with nothing in the numbers to say so, so a 120-minute cup tie reports
inflated shots, corners and tackles. Fitted beside 90-minute matches it drags every team-total model
upward and makes cup fixtures look fast-paced.

`provider.apifootball.exclude_extra_time` defaults on. The match is still ingested, still shown,
still graded — it is only kept out of the frame `engine_bridge.build_frames` fits, by one filter
there on the `extra_time` flag `match_row` sets. It is a setting rather than a constant so the
choice can be measured; with it off, the issue text says the models are being biased rather than
going quiet.

## Pinned

`tests/selftest_normalize_af.py`, 55 checks on a realistic bundled fixture. The guard gets the most,
in both directions: a null reading 0 where the match tracked that number, a null staying `None`
where nobody has it, and the across-the-fixture case where one away player's number settles a home
player's null.

One of those tests was wrong when first written, and the way it was wrong is worth keeping: it gave
the home side no shots while the away side had them, and expected a refusal. The guard correctly
read the home nulls as real zeros and summed a legitimate 0. The test now covers both — shots
untracked everywhere is refused, and a side that genuinely took none in a match that tracked them
sums to 0.
