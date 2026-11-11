# cricket-odds-collector

Paper-trading only. This repo collects match-winner odds for cricket. It does not place bets, hold a bookmaker account, or spend real money.

The collector (`07_odds_collector.py`) talks to The Odds API and appends rows to `odds_log.csv`. It only spends API credits when a snapshot is due:

- **open**: first snapshot of each UTC day (pauses for 3 days if a sport returns nothing)
- **bet**: 30–60 minutes before a match starts
- **close**: 3–20 minutes before the start (closing line)

GitHub Actions runs the collector every 10 minutes and commits `odds_log.csv` and `odds_state.json` only when they change. Credits per call equal the number of sports times the number of regions. This workflow uses `ODDS_SPORT=cricket_big_bash,cricket_odi,cricket_international_t20` and `ODDS_REGIONS=eu` (about 3 credits per snapshot). The free plan is 500 credits a month. Set the `ODDS_API_KEY` repository secret (never commit the key).

`08_build_odds.py` is a later step that turns a finished log into `odds.csv` for the paper trader. It needs pandas and a `matches.csv` file, and is not run by Actions.

Notes:

- GitHub can delay scheduled cron by several minutes, so an occasional snapshot window may be missed. You can also run the workflow by hand (Actions → odds-collector → Run workflow).
- GitHub disables scheduled workflows after 60 days with no repository activity. Commits from this workflow count as activity.
