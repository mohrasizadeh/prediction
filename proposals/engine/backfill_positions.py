"""One-off: fill player_match_stats.pos and players.pos from the saved lineups (same rule as normalize.lineup_pos)."""
import collections
import os
import sys

sys.path.insert(0, "/app/backend")
from pymongo import MongoClient, UpdateOne

import normalize as N
import settings_store as S


def run(db) -> dict:
    pmap = S.get(db, "provider.position_map")
    lpos = {(x["match_iid"], x["player_iid"]): N.lineup_pos(x, pmap) for x in db.lineups.find({}, {"_id": 0})}
    ops, per_player = [], collections.defaultdict(collections.Counter)
    for r in db.player_match_stats.find({"pos": None}, {"match_iid": 1, "player_iid": 1}):
        pos = lpos.get((r["match_iid"], r["player_iid"]))
        if pos:
            ops.append(UpdateOne({"_id": r["_id"]}, {"$set": {"pos": pos, **({"tackles": None} if pos == "GK" else {})}}))
            per_player[r["player_iid"]][pos] += 1
    if ops:
        db.player_match_stats.bulk_write(ops)
    pops = [UpdateOne({"iid": pid, "pos": None}, {"$set": {"pos": c.most_common(1)[0][0]}}) for pid, c in per_player.items()]
    if pops:
        db.players.bulk_write(pops)
    return {"rows": len(ops), "players": len(pops)}


if __name__ == "__main__":
    print(run(MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]))
