"""
Supabase sync loader — pushes dbt mart tables from BigQuery to Supabase.

Usage:
    from pipeline.loaders.supabase_loader import sync_season_to_supabase
    sync_season_to_supabase("2023")

All syncs are idempotent: rows are UPSERTed using the primary key columns
defined in MART_PRIMARY_KEYS. Running twice produces the same result.
"""

import logging
import math
import os

import pandas as pd
from google.cloud import bigquery
from supabase import create_client, Client

from pipeline.config import GCP_PROJECT_ID

logger = logging.getLogger(__name__)

# Columns to SELECT from each mart, in order. Must match the Supabase DDL
# in docs/supabase_schema.sql exactly. Update both if mart columns change.
MART_COLUMNS: dict[str, list[str]] = {
    "mart_league_standings": [
        "team", "league", "season", "matches_played", "wins", "draws", "losses",
        "points", "goals_for", "goals_against", "goal_difference",
        "total_xg_for", "total_xg_against", "total_xg_difference",
        "avg_ppda", "avg_deep_completions", "win_rate",
    ],
    "mart_winning_profiles": [
        "league", "season", "match_result", "is_home", "matches",
        "avg_goals_scored", "avg_goals_conceded",
        "avg_xg_for", "avg_xg_against", "avg_xg_diff",
        "avg_np_xg_for", "avg_np_xg_against",
        "avg_ppda", "avg_opponent_ppda", "avg_ppda_diff",
        "avg_deep_completions", "avg_opponent_deep_completions",
        "stddev_xg_for", "stddev_ppda",
    ],
    "mart_player_performance": [
        "player_name", "team", "league", "season",
        "match_appearances", "total_minutes",
        "total_goals", "total_assists", "total_own_goals", "total_shots",
        "total_xg", "total_xa", "total_xg_chain", "total_xg_buildup",
        "xg_per_90", "goals_per_90",
        "total_key_passes", "total_yellow_cards", "total_red_cards",
        "primary_position",
    ],
    "mart_tactical_analysis": [
        "team", "league", "season", "matches_played",
        "avg_ppda", "best_ppda", "worst_ppda", "ppda_consistency",
        "avg_opponent_ppda", "avg_deep_completions", "total_deep_completions",
        "avg_xg_for", "avg_np_xg_for", "wins", "win_rate",
    ],
    "mart_team_comparison": [
        "team", "league", "season", "matches_played",
        "wins", "draws", "losses", "points",
        "goals_for", "goals_against", "goal_difference",
        "total_xg_for", "total_xg_against",
        "avg_xg_for", "avg_xg_against",
        "avg_ppda", "avg_deep_completions", "win_rate",
        "xg_for_z", "ppda_z", "deep_completions_z",
    ],
    "mart_head_to_head": [
        "team_a", "team_b", "league", "season",
        "matches_played", "team_a_wins", "draws", "team_b_wins",
        "team_a_goals", "team_b_goals", "team_a_goal_difference",
        "team_a_avg_xg", "team_b_avg_xg",
        "team_a_win_rate", "team_b_win_rate",
    ],
}

# Columns used for ON CONFLICT resolution — must have a UNIQUE constraint
# in the Supabase schema (see docs/supabase_schema.sql).
MART_PRIMARY_KEYS: dict[str, list[str]] = {
    "mart_league_standings":   ["team", "league", "season"],
    "mart_winning_profiles":   ["league", "season", "match_result", "is_home"],
    "mart_player_performance": ["player_name", "team", "league", "season"],
    "mart_tactical_analysis":  ["team", "league", "season"],
    "mart_team_comparison":    ["team", "league", "season"],
    "mart_head_to_head":       ["team_a", "team_b", "league", "season"],
}

_UPSERT_BATCH_SIZE = 500  # Supabase recommends <= 1000 rows per request


def _get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    return create_client(url, key)


def _read_mart(bq_client: bigquery.Client, mart: str, season: str) -> pd.DataFrame:
    cols = ", ".join(MART_COLUMNS[mart])
    sql = (
        f"SELECT {cols} "
        f"FROM `{GCP_PROJECT_ID}.marts.{mart}` "
        f"WHERE season = '{season}'"
    )
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry = bq_client.query(sql, job_config=job_config)
    logger.info(
        f"BQ read dry-run {mart}/season={season}: "
        f"{dry.total_bytes_processed / 1e6:.3f} MB"
    )
    return bq_client.query(sql).to_dataframe()


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-serialisable list of dicts."""
    records = []
    for row in df.itertuples(index=False):
        rec = {}
        for col, val in zip(df.columns, row):
            # Convert numpy/pandas scalars to native Python types
            if hasattr(val, "item"):
                val = val.item()
            # Convert pandas NA / float NaN to None for JSON
            if val is pd.NA or (isinstance(val, float) and math.isnan(val)):
                val = None
            rec[col] = val
        records.append(rec)
    return records


def _upsert_table(
    sb: Client, mart: str, records: list[dict]
) -> None:
    pk_cols = ",".join(MART_PRIMARY_KEYS[mart])
    total = len(records)
    uploaded = 0
    for i in range(0, total, _UPSERT_BATCH_SIZE):
        batch = records[i : i + _UPSERT_BATCH_SIZE]
        sb.table(mart).upsert(batch, on_conflict=pk_cols).execute()
        uploaded += len(batch)
        logger.info(f"  {mart}: upserted {uploaded}/{total} rows")


def sync_season_to_supabase(season: str) -> None:
    """Sync all mart tables for a given season from BigQuery to Supabase."""
    bq_client = bigquery.Client(project=GCP_PROJECT_ID)
    sb = _get_supabase_client()

    for mart in MART_COLUMNS:
        logger.info(f"Syncing {mart} / season={season} → Supabase")
        df = _read_mart(bq_client, mart, season)
        if df.empty:
            logger.warning(f"  {mart}: no rows for season={season}, skipping")
            continue
        records = _to_records(df)
        _upsert_table(sb, mart, records)
        logger.info(f"  {mart}: done ({len(records)} rows)")

    logger.info(f"Supabase sync complete for season={season}")
