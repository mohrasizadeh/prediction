import sys, numpy as np, pandas as pd, pickle
sys.path.insert(0,'/home/claude/prediction/backend/soccer_brain')
from backtest_real import run_counts
lg = sys.argv[1]; since = sys.argv[2]; hl = sys.argv[3:]   # variants via half-life list
D = pd.read_csv('/tmp/bt/xg/data/Matches.csv', low_memory=False, parse_dates=['MatchDate'])
d = D[(D.Division==lg)&(D.MatchDate>='2012-07-01')&(D.MatchDate<='2026-07-01')].dropna(subset=['FTHome','HomeShots','HomeCorners','HomeFouls','HomeYellow','HomeTarget']).sort_values('MatchDate').reset_index(drop=True)
teams = sorted(set(d.HomeTeam)|set(d.AwayTeam)); ti={t:i for i,t in enumerate(teams)}
days = sorted(d.MatchDate.unique()); rnd={x:i for i,x in enumerate(days)}
d['gid']=np.arange(len(d)); d['round']=d.MatchDate.map(rnd); d['h']=d.HomeTeam.map(ti); d['a']=d.AwayTeam.map(ti)
matches = pd.DataFrame({'game_id':d.gid,'round':d['round'],'home':d.h,'away':d.a,'hg':d.FTHome,'ag':d.FTAway})
def side(me, op, sfx_me, sfx_op, home):
    return pd.DataFrame({'game_id':d.gid,'round':d['round'],'team':d[me],'opp':d[op],'home':home,
      'goals':d['FT'+sfx_me].astype(float),'goals_against':d['FT'+sfx_op].astype(float),
      'shots':d[sfx_me+'Shots'],'shots_against':d[sfx_op+'Shots'],'sot':d[sfx_me+'Target'],'sot_against':d[sfx_op+'Target'],
      'corners':d[sfx_me+'Corners'],'corners_against':d[sfx_op+'Corners'],'tackles':0.0,'tackles_against':0.0,'poss':0.5,
      'fouls':d[sfx_me+'Fouls'],'fouls_against':d[sfx_op+'Fouls'],'yellow':d[sfx_me+'Yellow'],'yellow_against':d[sfx_op+'Yellow']})
tg = pd.concat([side('h','a','Home','Away',1), side('a','h','Away','Home',0)], ignore_index=True)
pg = pd.DataFrame({'game_id':tg.game_id,'round':tg['round'],'player':tg.team,'team':tg.team,'opp':tg.opp,'pos':'MID','minutes':90.0,'started':1,
   'shots':tg.shots/11,'sot':tg.sot/11,'tackles':0.0,'team_shots':tg.shots,'team_sot':tg.sot,'team_tackles':1.0})
first = min(rnd[x] for x in days if x >= np.datetime64(since))
variants = {f'rb{h}': dict(half_life_rounds=20.0, extra_stats=('fouls','yellow'), ratings_blend=float(h)) for h in hl}
res = run_counts(matches, tg, pg, variants, stats=('shots','sot','corners','fouls','yellow'), burn=first, refit_every=6, n_draws=10, verbose=True)
res['gid']=res.game_id
res.to_pickle(f'/tmp/bt/eng_{lg}_{"_".join(hl)}.pkl'); print(len(res))
