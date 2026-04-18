from google.cloud import bigquery
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()
client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID"))

def run_query(sql, label):
    print(f"\n{'='*50}")
    print(f"QUERY: {label}")
    print('='*50)
    df = client.query(sql).to_dataframe()
    print(df.to_string(index=False))
    return df

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