"""Step 8: turn odds_log.csv into odds.csv for the paper trader (step 3).

Joins collected odds to finished matches in matches.csv by IST date + team names.
Prefers Pinnacle odds when present (sharpest bookmaker), else the median across books.
  bet odds   = the 'bet' snapshot (30-60 min before start, about when toss/XIs are known)
               or with --use-open, the morning 'open' snapshot (for a model that doesn't use the toss)
  close odds = the 'close' snapshot (3-20 min before start)
Usage: python 08_build_odds.py [--use-open]
"""
import statistics, sys
from datetime import timedelta
import pandas as pd

RENAME = {
    "delhi daredevils": "delhi capitals", "kings xi punjab": "punjab kings",
    "royal challengers bangalore": "royal challengers bengaluru",
    "rising pune supergiants": "rising pune supergiant",
}
norm = lambda t: RENAME.get(str(t).lower().strip(), str(t).lower().strip())

def pick(snap):
    """One (odds_home, odds_away) per snapshot: Pinnacle if present else median across books."""
    pin = snap[snap.bookmaker == "pinnacle"]
    if len(pin):
        return pin.odds_home.iloc[0], pin.odds_away.iloc[0]
    return snap.odds_home.median(), snap.odds_away.median()

def main():
    use_open = "--use-open" in sys.argv
    log = pd.read_csv("odds_log.csv")
    log["commence"] = pd.to_datetime(log.commence_utc, utc=True)
    log["ist_date"] = (log.commence + timedelta(hours=5, minutes=30)).dt.strftime("%Y-%m-%d")
    m = pd.read_csv("matches.csv")
    m["key"] = m.apply(lambda r: (r.date, frozenset([norm(r.team1), norm(r.team2)])), axis=1)
    lookup = {k: r for k, r in zip(m.key, m.itertuples())}
    def find(date, teams):   # local match date can differ from the IST date by a day
        d0 = pd.Timestamp(date)
        for off in (0, -1, 1):
            hit = lookup.get(((d0 + pd.Timedelta(days=off)).strftime("%Y-%m-%d"), teams))
            if hit is not None:
                return hit
    bet_kind = "open" if use_open else "bet"
    rows = []
    for eid, ev in log.groupby("event_id"):
        home, away = norm(ev.home.iloc[0]), norm(ev.away.iloc[0])
        match = find(ev.ist_date.iloc[0], frozenset([home, away]))
        if match is None:
            continue
        got = {}
        for kind in (bet_kind, "close"):
            k = ev[ev.kind == kind]
            if len(k):
                last = k[k.snapshot_utc == k.snapshot_utc.max()]   # latest snapshot of that kind
                got[kind] = pick(last)
        if len(got) < 2:
            continue
        flip = norm(match.team1) != home      # team1 in matches.csv may be the Odds API "away" team
        f = lambda t: (t[1], t[0]) if flip else t
        (b1, b2), (c1, c2) = f(got[bet_kind]), f(got["close"])
        rows.append({"match_id": match.match_id, "odds_team1": b1, "odds_team2": b2,
                     "close_team1": c1, "close_team2": c2})
    out = pd.DataFrame(rows)
    out.to_csv("odds.csv", index=False)
    print(f"{len(out)} matches with both bet-time and closing odds -> odds.csv")
    if len(out) < 100:
        print("Fewer than ~100 matches: too few for conclusions. Keep collecting (a full IPL season is ~74).")

if __name__ == "__main__":
    main()
