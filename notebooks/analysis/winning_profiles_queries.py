"""
Football Analytics — Winning Profile Analysis
==============================================
6 queries against mart_winning_profiles and mart_league_standings.
Dataset: 18,085 matches, 5 leagues, 10 seasons (2014–2023).

Run from the project root:
    python notebooks/analysis/winning_profiles_queries.py
"""

import os
from dotenv import load_dotenv
from google.cloud import bigquery
from pipeline.config import GCP_PROJECT_ID

load_dotenv()

client = bigquery.Client(project=GCP_PROJECT_ID)
P = f"`{GCP_PROJECT_ID}.marts"


def run(sql: str) -> list:
    return list(client.query(sql).result())


# =============================================================================
# Q1 — Core winning profile: how do the key metrics differ across results?
# Aggregated across all 5 leagues and all 10 seasons.
# =============================================================================
print("\n" + "=" * 70)
print("Q1 — Core winning profile (all leagues, all seasons)")
print("=" * 70)
rows = run(f"""
SELECT
    match_result,
    SUM(matches)                                        AS total_matches,
    ROUND(AVG(avg_xg_for),          3)                 AS xg_for,
    ROUND(AVG(avg_xg_against),      3)                 AS xg_against,
    ROUND(AVG(avg_xg_diff),         3)                 AS xg_diff,
    ROUND(AVG(avg_np_xg_for),       3)                 AS np_xg_for,
    ROUND(AVG(avg_ppda),            3)                 AS ppda,
    ROUND(AVG(avg_opponent_ppda),   3)                 AS opp_ppda,
    ROUND(AVG(avg_deep_completions),1)                 AS deep_completions,
    ROUND(AVG(avg_goals_scored),    3)                 AS goals_scored
FROM {P}.mart_winning_profiles`
GROUP BY match_result
ORDER BY CASE match_result WHEN 'win' THEN 1 WHEN 'draw' THEN 2 ELSE 3 END
""")
print(f"{'result':<8} {'matches':>8} {'xg_for':>8} {'xg_vs':>7} {'xg_diff':>8} "
      f"{'np_xg':>7} {'ppda':>7} {'opp_ppda':>9} {'deep':>6} {'goals':>7}")
print("-" * 75)
for r in rows:
    print(f"{r.match_result:<8} {r.total_matches:>8,} {r.xg_for:>8} {r.xg_against:>7} "
          f"{r.xg_diff:>8} {r.np_xg_for:>7} {r.ppda:>7} {r.opp_ppda:>9} "
          f"{r.deep_completions:>6} {r.goals_scored:>7}")


# =============================================================================
# Q2 — Home advantage in winning profiles
# =============================================================================
print("\n" + "=" * 70)
print("Q2 — Home vs away winning profiles")
print("=" * 70)
rows = run(f"""
SELECT
    match_result,
    is_home,
    SUM(matches)                                        AS total_matches,
    ROUND(AVG(avg_xg_for),          3)                 AS xg_for,
    ROUND(AVG(avg_ppda),            3)                 AS ppda,
    ROUND(AVG(avg_deep_completions),1)                 AS deep_completions,
    ROUND(AVG(avg_goals_scored),    3)                 AS goals_scored
FROM {P}.mart_winning_profiles`
GROUP BY match_result, is_home
ORDER BY CASE match_result WHEN 'win' THEN 1 WHEN 'draw' THEN 2 ELSE 3 END, is_home DESC
""")
print(f"{'result':<8} {'home':>6} {'matches':>8} {'xg_for':>8} {'ppda':>7} {'deep':>6} {'goals':>7}")
print("-" * 55)
for r in rows:
    home_str = "home" if r.is_home else "away"
    print(f"{r.match_result:<8} {home_str:>6} {r.total_matches:>8,} {r.xg_for:>8} "
          f"{r.ppda:>7} {r.deep_completions:>6} {r.goals_scored:>7}")


# =============================================================================
# Q3 — League variation: does the "winning formula" differ by league?
# =============================================================================
print("\n" + "=" * 70)
print("Q3 — Winning profile by league (wins only, all seasons)")
print("=" * 70)
rows = run(f"""
SELECT
    league,
    SUM(matches)                                        AS win_matches,
    ROUND(AVG(avg_xg_for),          3)                 AS avg_xg_for,
    ROUND(AVG(avg_ppda),            3)                 AS avg_ppda,
    ROUND(AVG(avg_deep_completions),1)                 AS avg_deep,
    ROUND(AVG(avg_goals_scored),    3)                 AS avg_goals
FROM {P}.mart_winning_profiles`
WHERE match_result = 'win'
GROUP BY league
ORDER BY avg_xg_for DESC
""")
print(f"{'league':<20} {'wins':>7} {'xg_for':>8} {'ppda':>7} {'deep':>6} {'goals':>7}")
print("-" * 55)
for r in rows:
    print(f"{r.league:<20} {r.win_matches:>7,} {r.avg_xg_for:>8} {r.avg_ppda:>7} "
          f"{r.avg_deep:>6} {r.avg_goals:>7}")


# =============================================================================
# Q4 — Temporal trend: have winning team characteristics changed over 10 seasons?
# =============================================================================
print("\n" + "=" * 70)
print("Q4 — Temporal trend: winning profiles by season (all leagues)")
print("=" * 70)
rows = run(f"""
SELECT
    season,
    SUM(matches)                                        AS win_matches,
    ROUND(AVG(avg_xg_for),          3)                 AS avg_xg_for,
    ROUND(AVG(avg_ppda),            3)                 AS avg_ppda,
    ROUND(AVG(avg_deep_completions),1)                 AS avg_deep,
    ROUND(AVG(avg_np_xg_for),       3)                 AS avg_np_xg
FROM {P}.mart_winning_profiles`
WHERE match_result = 'win'
GROUP BY season
ORDER BY season
""")
print(f"{'season':<8} {'wins':>7} {'xg_for':>8} {'np_xg':>7} {'ppda':>7} {'deep':>6}")
print("-" * 50)
for r in rows:
    print(f"{r.season:<8} {r.win_matches:>7,} {r.avg_xg_for:>8} {r.avg_np_xg:>7} "
          f"{r.avg_ppda:>7} {r.avg_deep:>6}")


# =============================================================================
# Q5 — Discriminating power: which metric has the biggest gap between win/loss?
# Expressed as (win_value - loss_value) / loss_value * 100 = % lift
# =============================================================================
print("\n" + "=" * 70)
print("Q5 — Metric discriminating power: % lift of wins over losses")
print("=" * 70)
rows = run(f"""
WITH pivoted AS (
    SELECT
        MAX(CASE WHEN match_result = 'win'  THEN avg_xg_for END)          AS win_xg_for,
        MAX(CASE WHEN match_result = 'loss' THEN avg_xg_for END)          AS loss_xg_for,
        MAX(CASE WHEN match_result = 'win'  THEN avg_np_xg_for END)       AS win_np_xg,
        MAX(CASE WHEN match_result = 'loss' THEN avg_np_xg_for END)       AS loss_np_xg,
        MAX(CASE WHEN match_result = 'win'  THEN avg_ppda END)            AS win_ppda,
        MAX(CASE WHEN match_result = 'loss' THEN avg_ppda END)            AS loss_ppda,
        MAX(CASE WHEN match_result = 'win'  THEN avg_deep_completions END) AS win_deep,
        MAX(CASE WHEN match_result = 'loss' THEN avg_deep_completions END) AS loss_deep,
        MAX(CASE WHEN match_result = 'win'  THEN avg_goals_scored END)    AS win_goals,
        MAX(CASE WHEN match_result = 'loss' THEN avg_goals_scored END)    AS loss_goals
    FROM {P}.mart_winning_profiles`
)
SELECT
    ROUND(SAFE_DIVIDE(win_xg_for  - loss_xg_for,  loss_xg_for)  * 100, 1) AS xg_for_pct_lift,
    ROUND(SAFE_DIVIDE(win_np_xg   - loss_np_xg,   loss_np_xg)   * 100, 1) AS np_xg_pct_lift,
    ROUND(SAFE_DIVIDE(loss_ppda   - win_ppda,      win_ppda)     * 100, 1) AS ppda_pct_better,
    ROUND(SAFE_DIVIDE(win_deep    - loss_deep,     loss_deep)    * 100, 1) AS deep_pct_lift,
    ROUND(SAFE_DIVIDE(win_goals   - loss_goals,    loss_goals)   * 100, 1) AS goals_pct_lift,
    ROUND(win_xg_for,  3)  AS win_xg_for,
    ROUND(loss_xg_for, 3)  AS loss_xg_for,
    ROUND(win_ppda,    3)  AS win_ppda,
    ROUND(loss_ppda,   3)  AS loss_ppda
FROM pivoted
""")
for r in rows:
    print(f"xG for:           wins={r.win_xg_for}  losses={r.loss_xg_for}  → +{r.xg_for_pct_lift}% lift")
    print(f"np_xG for:        +{r.np_xg_pct_lift}% lift")
    print(f"PPDA (pressing):  wins={r.win_ppda}  losses={r.loss_ppda}  → {r.ppda_pct_better}% more aggressive")
    print(f"Deep completions: +{r.deep_pct_lift}% lift")
    print(f"Goals scored:     +{r.goals_pct_lift}% lift")


# =============================================================================
# Q6 — xG efficiency: do winners create more OR convert better?
# Compare xG created vs actual goals to isolate chance creation from finishing
# =============================================================================
print("\n" + "=" * 70)
print("Q6 — xG efficiency: chance creation vs finishing")
print("=" * 70)
rows = run(f"""
SELECT
    match_result,
    ROUND(AVG(avg_xg_for),       3)  AS avg_xg_created,
    ROUND(AVG(avg_goals_scored), 3)  AS avg_goals,
    ROUND(SAFE_DIVIDE(AVG(avg_goals_scored), AVG(avg_xg_for)), 3) AS goals_per_xg,
    ROUND(AVG(avg_xg_against),   3)  AS avg_xg_allowed,
    ROUND(AVG(avg_goals_conceded),3) AS avg_goals_conceded,
    ROUND(SAFE_DIVIDE(AVG(avg_goals_conceded), AVG(avg_xg_against)), 3) AS conceded_per_xg_allowed
FROM {P}.mart_winning_profiles`
GROUP BY match_result
ORDER BY CASE match_result WHEN 'win' THEN 1 WHEN 'draw' THEN 2 ELSE 3 END
""")
print(f"{'result':<8} {'xg_created':>12} {'goals':>7} {'goals/xg':>10} "
      f"{'xg_allowed':>11} {'conceded':>9} {'conceded/xg':>12}")
print("-" * 75)
for r in rows:
    print(f"{r.match_result:<8} {r.avg_xg_created:>12} {r.avg_goals:>7} "
          f"{r.goals_per_xg:>10} {r.avg_xg_allowed:>11} "
          f"{r.avg_goals_conceded:>9} {r.conceded_per_xg_allowed:>12}")
