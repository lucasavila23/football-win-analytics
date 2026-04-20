from google.cloud import bigquery
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()
client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID"))
P = f"`{os.getenv('GCP_PROJECT_ID')}.marts"

def run_query(sql, label):
    print(f"\n{'='*50}")
    print(f"QUERY: {label}")
    print('='*50)
    df = client.query(sql).to_dataframe()
    print(df.to_string(index=False))
    return df

def run(sql: str):
    return list(client.query(sql).result())

# Query 1 — Pressing
q1 = """
SELECT
    match_result,
    ROUND(AVG(avg_ppda), 2) AS avg_ppda,
    ROUND(AVG(avg_opponent_ppda), 2) AS avg_opponent_ppda,
    ROUND(AVG(avg_ppda_diff), 2) AS avg_ppda_diff,
    COUNT(*) AS sample_size
FROM `marts.mart_winning_profiles`
GROUP BY match_result
ORDER BY match_result
"""

# Query 2 — xG creation
q2 = """
SELECT
    match_result,
    ROUND(AVG(avg_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(avg_xg_against), 2) AS avg_xg_against,
    ROUND(AVG(avg_xg_diff), 2) AS avg_xg_diff,
    COUNT(*) AS sample_size
FROM `marts.mart_winning_profiles`
GROUP BY match_result
ORDER BY match_result
"""

# Query 3 — Goals vs xG efficiency
q3 = """
SELECT
    match_result,
    ROUND(AVG(avg_goals_scored), 2) AS avg_goals,
    ROUND(AVG(avg_xg_for), 2) AS avg_xg,
    ROUND(AVG(avg_goals_scored) / NULLIF(AVG(avg_xg_for), 0), 2) AS goals_per_xg_ratio,
    COUNT(*) AS sample_size
FROM `marts.mart_winning_profiles`
GROUP BY match_result
ORDER BY match_result
"""

# Query 4 — Home advantage
q4 = """
SELECT
    match_result,
    is_home,
    ROUND(AVG(avg_ppda), 2) AS avg_ppda,
    ROUND(AVG(avg_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(avg_goals_scored), 2) AS avg_goals,
    COUNT(*) AS sample_size
FROM `marts.mart_winning_profiles`
GROUP BY match_result, is_home
ORDER BY match_result, is_home
"""

# Query 5 — By league
q5 = """
SELECT
    league,
    match_result,
    ROUND(AVG(avg_ppda), 2) AS avg_ppda,
    ROUND(AVG(avg_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(avg_xg_diff), 2) AS avg_xg_diff,
    COUNT(*) AS sample_size
FROM `marts.mart_winning_profiles`
GROUP BY league, match_result
ORDER BY league, match_result
"""

# Query 6 — Territorial dominance (possession proxy)
q6 = """
SELECT
    match_result,
    ROUND(AVG(avg_deep_completions), 2) AS avg_deep_completions,
    ROUND(AVG(avg_opponent_deep_completions), 2) AS avg_opponent_deep_completions,
    ROUND(AVG(avg_deep_completions) - AVG(avg_opponent_deep_completions), 2) AS deep_completion_advantage,
    COUNT(*) AS sample_size
FROM `marts.mart_winning_profiles`
GROUP BY match_result
ORDER BY match_result
"""

# Run all
df1 = run_query(q1, "Pressing vs Result")
df2 = run_query(q2, "xG Creation vs Result")
df3 = run_query(q3, "Goals vs xG Efficiency")
df4 = run_query(q4, "Home Advantage Control")
df5 = run_query(q5, "Patterns by League")
df6 = run_query(q6, "Territorial Dominance vs Result")

# =============================================================================
# Q7 — Team rankings: which teams best exemplify the winning formula?
# =============================================================================
print("\n" + "=" * 70)
print("Q7 — Top teams by winning characteristic")
print("=" * 70)

# Top 5 by xG creation
print("\nTop 5 teams by xG creation (all seasons):")
rows = run(f"""
SELECT
    team,
    league,
    ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(points), 0) AS avg_points,
    ROUND(AVG(win_rate), 3) AS avg_win_rate
FROM `{os.getenv('GCP_PROJECT_ID')}.marts.mart_league_standings`
GROUP BY team, league
ORDER BY avg_xg_for DESC
LIMIT 5
""")
print(f"{'team':<20} {'league':<15} {'xg_for':>8} {'points':>7} {'win_rate':>10}")
print("-" * 60)
for r in rows:
    print(f"{r.team:<20} {r.league:<15} {r.avg_xg_for:>8} {r.avg_points:>7} {r.avg_win_rate:>10}")

# Top 5 by defensive solidity
print("\nTop 5 teams by defensive solidity (lowest xG against):")
rows = run(f"""
SELECT
    team,
    league,
    ROUND(AVG(total_xg_against), 2) AS avg_xg_against,
    ROUND(AVG(points), 0) AS avg_points,
    ROUND(AVG(win_rate), 3) AS avg_win_rate
FROM `{os.getenv('GCP_PROJECT_ID')}.marts.mart_league_standings`
GROUP BY team, league
ORDER BY avg_xg_against ASC
LIMIT 5
""")
print(f"{'team':<20} {'league':<15} {'xg_against':>11} {'points':>7} {'win_rate':>10}")
print("-" * 65)
for r in rows:
    print(f"{r.team:<20} {r.league:<15} {r.avg_xg_against:>11} {r.avg_points:>7} {r.avg_win_rate:>10}")

# Top 5 by pressing intensity
print("\nTop 5 teams by pressing intensity (lowest avg PPDA):")
rows = run(f"""
SELECT
    team,
    league,
    ROUND(AVG(avg_ppda), 2) AS avg_ppda,
    ROUND(AVG(points), 0) AS avg_points,
    ROUND(AVG(win_rate), 3) AS avg_win_rate
FROM `{os.getenv('GCP_PROJECT_ID')}.marts.mart_league_standings`
GROUP BY team, league
ORDER BY avg_ppda ASC
LIMIT 5
""")
print(f"{'team':<20} {'league':<15} {'ppda':>7} {'points':>7} {'win_rate':>10}")
print("-" * 58)
for r in rows:
    print(f"{r.team:<20} {r.league:<15} {r.avg_ppda:>7} {r.avg_points:>7} {r.avg_win_rate:>10}")


# =============================================================================
# Q8 — Outliers: teams that break the winning formula
# =============================================================================
print("\n" + "=" * 70)
print("Q8 — Outliers: teams that win/lose against expectations")
print("=" * 70)

# High win rate with LOW xG (efficient/lucky)
print("\nHigh-winning teams with LOW xG (efficiency > chance creation):")
rows = run(f"""
SELECT
    team,
    league,
    ROUND(AVG(win_rate), 3) AS avg_win_rate,
    ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(points), 0) AS avg_points
FROM `{os.getenv('GCP_PROJECT_ID')}.marts.mart_league_standings`
GROUP BY team, league
HAVING AVG(win_rate) > 0.4 AND AVG(total_xg_for) < 40
ORDER BY avg_win_rate DESC
LIMIT 5
""")
print(f"{'team':<20} {'league':<15} {'win_rate':>10} {'xg_for':>8} {'points':>7}")
print("-" * 60)
for r in rows:
    print(f"{r.team:<20} {r.league:<15} {r.avg_win_rate:>10} {r.avg_xg_for:>8} {r.avg_points:>7}")

# High xG but LOW win rate (unlucky)
print("\nHigh xG teams with LOW win rate (chance creation > results):")
rows = run(f"""
SELECT
    team,
    league,
    ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(win_rate), 3) AS avg_win_rate,
    ROUND(AVG(points), 0) AS avg_points
FROM `{os.getenv('GCP_PROJECT_ID')}.marts.mart_league_standings`
GROUP BY team, league
HAVING AVG(total_xg_for) > 50 AND AVG(win_rate) < 0.35
ORDER BY avg_xg_for DESC
LIMIT 5
""")
print(f"{'team':<20} {'league':<15} {'xg_for':>8} {'win_rate':>10} {'points':>7}")
print("-" * 60)
for r in rows:
    print(f"{r.team:<20} {r.league:<15} {r.avg_xg_for:>8} {r.avg_win_rate:>10} {r.avg_points:>7}")


# =============================================================================
# Q9 — Temporal trend: have winning characteristics evolved over 10 seasons?
# =============================================================================
print("\n" + "=" * 70)
print("Q9 — Temporal evolution: league-wide winning metrics by season")
print("=" * 70)
rows = run(f"""
SELECT
    season,
    ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
    ROUND(AVG(total_xg_against), 2) AS avg_xg_against,
    ROUND(AVG(avg_ppda), 2) AS avg_ppda,
    ROUND(AVG(avg_deep_completions), 1) AS avg_deep,
    ROUND(AVG(win_rate), 3) AS avg_win_rate
FROM `{os.getenv('GCP_PROJECT_ID')}.marts.mart_league_standings`
GROUP BY season
ORDER BY season
""")
print(f"{'season':<8} {'xg_for':>8} {'xg_against':>11} {'ppda':>7} {'deep':>6} {'win_rate':>10}")
print("-" * 60)
for r in rows:
    print(f"{r.season:<8} {r.avg_xg_for:>8} {r.avg_xg_against:>11} {r.avg_ppda:>7} "
          f"{r.avg_deep:>6} {r.avg_win_rate:>10}")