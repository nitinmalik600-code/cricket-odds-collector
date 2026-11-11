"""Step 7: free, credit-efficient odds collector (The Odds API, match-winner odds).

Run it often (every 10 minutes is fine): it only spends an API credit when it
actually needs a snapshot, otherwise it exits immediately.
  open  : first snapshot of each UTC day (skipped for 3 days after an empty result, so an
          off-season tournament costs almost nothing)
  bet   : a match starts in 30-60 minutes (about when XIs/toss are known)
  close : a match starts in 3-20 minutes                       -> closing odds
Cost: about 2-3 calls per match day. Each call costs 1 credit per region
(free plan = 500 credits/month), so 2 regions for a whole IPL month fits.

Setup:  export ODDS_API_KEY=your_key      (free key at the-odds-api.com)
        python 07_odds_collector.py --list   # shows which cricket tournaments are live (free)
        python 07_odds_collector.py          # collect (what cron/GitHub Actions runs)
Env:    ODDS_SPORT (default cricket_ipl; several allowed, e.g. "cricket_international_t20,cricket_odi"),
        ODDS_REGIONS (default "eu,uk"). Credits per call = regions x sports.
        Tests have a Draw outcome: prefer T20 and ODI, where the h2h market is two-way.
Output: odds_log.csv (append-only, one row per bookmaker per snapshot)
"""
import csv, json, os, sys, statistics, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

LOG = "odds_log.csv"
STATE = "odds_state.json"      # remembers last open-snapshot day and credits left
BASE = "https://api.the-odds-api.com/v4"
SPORTS = [x.strip() for x in os.environ.get("ODDS_SPORT", "cricket_ipl").split(",") if x.strip()]
REGIONS = os.environ.get("ODDS_REGIONS", "eu,uk")
KEY = os.environ.get("ODDS_API_KEY", "")
WINDOWS = {"bet": (30, 60), "close": (3, 20)}      # minutes before start
MIN_CREDITS_LEFT = 40
IST = timezone(timedelta(hours=5, minutes=30))
FIELDS = ["snapshot_utc", "kind", "sport", "event_id", "commence_utc", "home", "away",
          "bookmaker", "odds_home", "odds_away", "mins_to_start"]

def call(path, **params):
    params["apiKey"] = KEY
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read()), r.headers

def read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, newline="") as f:
        return list(csv.DictReader(f))

def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def read_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}

def decide(rows, now, state):
    """Return the snapshot kind to take now, or None."""
    if state.get("credits_left", 999) < MIN_CREDITS_LEFT:
        return None
    if state.get("last_open_utc") != str(now.date()) and str(now.date()) >= state.get("empty_until", ""):
        return "open"
    events = {r["event_id"]: parse_dt(r["commence_utc"]) for r in rows}
    for kind, (lo, hi) in WINDOWS.items():
        for eid, start in events.items():
            mins = (start - now).total_seconds() / 60
            if lo <= mins <= hi and not any(
                    r["event_id"] == eid and r["kind"] == kind for r in rows):
                return kind
    return None

def rows_from_response(events, kind, now, sport=""):
    out = []
    for e in events:
        mins = round((parse_dt(e["commence_time"]) - now).total_seconds() / 60)
        for bk in e.get("bookmakers", []):
            for m in bk.get("markets", []):
                if m["key"] != "h2h":
                    continue
                price = {o["name"]: o["price"] for o in m["outcomes"]}
                if e["home_team"] in price and e["away_team"] in price:
                    out.append({"snapshot_utc": now.isoformat(timespec="seconds"), "kind": kind, "sport": sport,
                                "event_id": e["id"], "commence_utc": e["commence_time"],
                                "home": e["home_team"], "away": e["away_team"], "bookmaker": bk["key"],
                                "odds_home": price[e["home_team"]], "odds_away": price[e["away_team"]],
                                "mins_to_start": mins})
    return out

def main():
    if not KEY:
        sys.exit("Set ODDS_API_KEY first (free key at the-odds-api.com).")
    if "--list" in sys.argv:
        sports, _ = call("/sports")
        for s in sports:
            if s["key"].startswith("cricket"):
                print(f"{s['key']:34s} {'IN SEASON' if s.get('active') else 'off season'}  {s['title']}")
        return
    now = datetime.now(timezone.utc)
    rows = read_log()
    state = read_state()
    kind = decide(rows, now, state)
    if kind is None:
        print("Nothing to snapshot right now (no credit spent).")  # also when credits are nearly gone
        return
    events, new, left = [], [], 999.0
    for sport in SPORTS:
        try:
            ev, hdr = call(f"/sports/{sport}/odds", regions=REGIONS, markets="h2h", oddsFormat="decimal")
        except Exception as e:      # e.g. tournament not available: skip it, keep the others
            print(f"{sport}: {e}")
            continue
        left = float(hdr.get("x-requests-remaining", left))
        events += ev
        new += rows_from_response(ev, kind, now, sport)
    new_file = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(new)
    state["credits_left"] = left
    if kind == "open":
        state["last_open_utc"] = str(now.date())
    if not events:
        state["empty_until"] = str((now + timedelta(days=3)).date())
    else:
        state.pop("empty_until", None)
    json.dump(state, open(STATE, "w"))
    print(f"[{kind}] {len(events)} matches, {len(new)} rows saved. Credits left this month: {left:.0f}")
    if left < MIN_CREDITS_LEFT:
        print("WARNING: credits almost used up - collector pauses below", MIN_CREDITS_LEFT)
    if not events:
        print("No upcoming matches returned (off season?). Next check in about 3 days.")

if __name__ == "__main__":
    main()
