# Football Analytics — Dev Log
# Big Data Analytics 2026 | Lucas Avila
# =============================================================================

---

## Dev Log #6 — 15th April 2026

### Summary
Completed the full dbt model DAG: three intermediate models, six mart models,
one custom macro, and two singular tests. All 12 models materialized and all
18 data tests pass first run with zero fixes required.

---

### What was built

#### Intermediate layer

**`int_team_match_aggregates`** (760 rows for La Liga 2023)
The core unpivot model. One row per match in `stg_matches` becomes two rows —
home team perspective and away team perspective — via `UNION ALL`. This is the
foundation for every standings, profile, and tactical mart.
Key decision: `score_diff` and `xg_diff` are negated for the away team's row
so that "positive = better for this team" holds universally downstream.
`match_result` (win/loss/draw) and `points` (3/1/0) are derived here, not
in staging, because they require knowing both sides of the score.

**`int_winning_matches`** (273 rows — 71.8% win rate for La Liga 2023 home + away)
Simple filter on `int_team_match_aggregates` WHERE `match_result = 'win'`.
Exists as a named model rather than an inline CTE to make the winning-profile
mart readable and to allow independent testing later.

**`int_head_to_head`** (190 rows — C(20,2) = 190 unique La Liga pairings 2023)
Canonical pair ordering via `CASE WHEN team < opponent THEN team ELSE opponent END`
prevents duplicate (A vs B) / (B vs A) pairs. Aggregates wins, draws, goals,
and avg xG per pair per league per season.

---

#### Mart layer

**`mart_league_standings`** (20 rows — one per La Liga team)
Classic points table: played, wins, draws, losses, points, GF, GA, GD, total
xG for/against/diff, avg PPDA, avg deep completions, win rate.
Uses the `calculate_win_rate` macro (SAFE_DIVIDE wrapper) to guard against
division by zero on teams with zero matches (impossible in practice but
defensively correct).

**`mart_winning_profiles`** (6 rows — win/draw/loss × home/away)
The project's core analytical output. Groups `int_team_match_aggregates` by
`(league, season, match_result, is_home)` and computes average and stddev of
all key metrics. Designed to answer: "What do winning teams look like, and how
does that differ at home vs away?"

**`mart_player_performance`** (72 rows — aggregated from 1,000-row staging LIMIT)
Season-level player aggregation. Groups by `player_name + team + league + season`
(immutable rule from CLAUDE.md — never group by player_name alone due to
transfers and multi-league appearances).
Uses `APPROX_TOP_COUNT(position, 1)[OFFSET(0)].value` for primary position —
BigQuery's approximate mode function. `xg_per_90` and `goals_per_90` computed
with SAFE_DIVIDE to handle players with zero minutes.

**`mart_tactical_analysis`** (20 rows — one per team)
PPDA-focused pressing intensity analysis. Includes avg/min/max/stddev PPDA,
opponent PPDA, deep completions totals, avg xG context, and win rate.
Ordered by avg_ppda ASC (lower = more aggressive press = more interesting).

**`mart_team_comparison`** (20 rows — one per team)
Cross-team comparison with league-relative z-scores. Two-CTE pattern:
`team_season` computes per-team aggregates; `league_stats` computes per-league
AVG and STDDEV for normalization. Z-scores computed for xG_for, PPDA
(inverted — lower PPDA = better = positive z), and deep completions.
Designed for the Supabase frontend "above average" indicators.

**`mart_head_to_head`** (190 rows — sourced from int_head_to_head)
Adds win rates for both team_a and team_b via the macro. Includes goal
difference from team_a's perspective. Ordered by matches_played DESC within
each league/season for rivalry relevance.

---

#### Macro: `calculate_win_rate`

```sql
{% macro calculate_win_rate(wins_col, matches_col) %}
    SAFE_DIVIDE({{ wins_col }}, {{ matches_col }})
{% endmacro %}
```

Thin wrapper around `SAFE_DIVIDE`. Exists to centralise the pattern and make
mart SQL self-documenting. Used in four marts.

---

#### Singular tests

**`assert_no_negative_xg`** — returns rows from `stg_matches` where
`home_xg < 0 OR away_xg < 0`. Empty result = pass. Guards against scraper
corruption in Understat xG values.

**`assert_match_has_two_teams`** — returns `(match_date, team, league, season)`
combinations from `int_team_match_aggregates` that appear more than once.
Empty result = pass. Guards against the UNION ALL producing duplicate rows
for any team in any match.

---

### Test results

```
dbt run  — PASS=12 WARN=0 ERROR=0 SKIP=0  (40s, La Liga 2023)
dbt test — PASS=18 WARN=0 ERROR=0 SKIP=0  (25s)
```

Row counts:
- `stg_matches`: 380 rows (La Liga 2023, 380 matches)
- `stg_player_stats`: 1,000 rows (LIMIT applied)
- `stg_lineups`: 1,000 rows (LIMIT applied)
- `int_team_match_aggregates`: 760 rows (380 × 2 perspectives)
- `int_winning_matches`: 273 rows
- `int_head_to_head`: 190 rows
- `mart_league_standings`: 20 rows
- `mart_tactical_analysis`: 20 rows
- `mart_team_comparison`: 20 rows
- `mart_winning_profiles`: 6 rows
- `mart_head_to_head`: 190 rows
- `mart_player_performance`: 72 rows

---

### Key architectural decisions made this session

1. **UNION ALL over PIVOT for team perspectives.** BigQuery PIVOT requires
   known column names at query time. UNION ALL is more readable, testable,
   and avoids coupling the transform to the home/away column naming in raw.

2. **`LIMIT` retained in all intermediate models for development.** Will be
   removed in the production pass before the GitHub Actions pipeline is wired.
   Decision to leave them in avoids accidental full-table scans during iteration.

3. **`mart_player_performance` aggregates at season granularity, not match.**
   The `raw.understat_player_stats` table has no match_date column (the
   scraper's `_normalise_players()` doesn't output it). Match-level player
   joins are deferred. Season aggregation is correct for the research question.

4. **Z-scores in `mart_team_comparison` use league-level baselines.**
   A team's xG z-score is relative to its own league, not all leagues combined.
   This makes inter-league comparison meaningful for frontend display.

5. **`calculate_win_rate` macro uses SAFE_DIVIDE, not a CASE/NULLIF guard.**
   BigQuery's SAFE_DIVIDE is cleaner and handles the zero case identically.
   The macro boundary also means any future change (e.g. adding a minimum
   matches threshold) is a one-line edit.

---

### Next steps

1. Remove `LIMIT` guards from all models before full backfill run
2. GitHub Actions `pipeline.yml` — orchestrate end-to-end pipeline
3. Supabase project setup and mart sync
4. Extend pipeline to remaining leagues (EPL, Bundesliga, Serie A, Ligue 1)
5. `pipeline.yml` for scheduled weekly refresh (current season 2024)

---

*Dev Log #6 — 15th April 2026 | Lucas Avila*
