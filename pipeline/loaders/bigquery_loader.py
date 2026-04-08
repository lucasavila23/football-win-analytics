# =============================================================================
# BIGQUERY LOADER
# =============================================================================
# Responsibility: Load Parquet files from GCS bronze into BigQuery raw dataset,
# and provide safe query utilities that enforce the GCP free-tier rules from
# CLAUDE.md.
#
# GCP FREE-TIER RULES ENFORCED HERE (non-negotiable):
#   1. Always dry-run before executing any query.
#      If estimated bytes > 10 GB → raise, never execute.
#   2. Never SELECT * on staging/intermediate/marts tables.
#   3. run_query() defaults to dry_run=True — caller must explicitly pass
#      dry_run=False to actually execute.
#   4. get_row_count() raises if dry-run estimate exceeds 1 GB.
#      (COUNT queries should never be that large.)
#
# BigQuery table naming convention in raw dataset:
#   {source}_{table}  e.g. understat_matches, espn_lineups, statsbomb_events
#
# Credentials: GOOGLE_APPLICATION_CREDENTIALS env var via load_dotenv().
# Client: always bigquery.Client(project=GCP_PROJECT_ID).
# =============================================================================

import logging

from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from pipeline.config import GCP_PROJECT_ID, GCS_BUCKET_NAME, BIGQUERY_DATASET_RAW

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Safety ceiling for all queries. Anything above this aborts before execution.
_QUERY_SAFETY_LIMIT_GB = 10.0
# Tighter ceiling for COUNT queries — they should never approach this.
_COUNT_QUERY_LIMIT_GB = 1.0


def _get_client() -> bigquery.Client:
    """Return a BigQuery client using the configured GCP project."""
    return bigquery.Client(project=GCP_PROJECT_ID)


def run_query(sql: str, dry_run: bool = True):
    """
    Execute a BigQuery SQL query with mandatory dry-run safety check.

    Default is dry_run=True — caller must explicitly pass dry_run=False
    to actually execute. Always logs estimated bytes before any execution.
    Raises if the estimate exceeds the 10 GB free-tier safety limit.

    Args:
        sql:      The SQL query string to execute.
        dry_run:  If True (default), only estimate bytes and return the estimate.
                  If False, execute the query after the safety check passes.

    Returns:
        float: estimated GB scanned (when dry_run=True)
        google.cloud.bigquery.table.RowIterator: query results (when dry_run=False)

    Raises:
        ValueError: if estimated bytes exceed _QUERY_SAFETY_LIMIT_GB (10 GB).
    """
    client = _get_client()

    # Always dry-run first to estimate cost
    dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_job = client.query(sql, job_config=dry_config)
    estimated_gb = dry_job.total_bytes_processed / 1e9

    logger.info(f"Estimated bytes: {estimated_gb:.3f} GB")

    if estimated_gb > _QUERY_SAFETY_LIMIT_GB:
        raise ValueError(
            f"Query would scan {estimated_gb:.1f} GB — "
            f"exceeds {_QUERY_SAFETY_LIMIT_GB} GB free-tier safety limit. Aborting."
        )

    if dry_run:
        return estimated_gb

    job = client.query(sql)
    return job.result()


def table_exists(dataset: str, table_name: str) -> bool:
    """
    Check whether a BigQuery table exists.

    Args:
        dataset:    BigQuery dataset name (e.g. 'raw', 'staging')
        table_name: Table name within the dataset (e.g. 'understat_matches')

    Returns:
        True if the table exists, False otherwise.
    """
    client = _get_client()
    table_ref = f"{GCP_PROJECT_ID}.{dataset}.{table_name}"
    try:
        client.get_table(table_ref)
        return True
    except NotFound:
        return False


def get_row_count(dataset: str, table_name: str) -> int:
    """
    Return the row count for a BigQuery table using COUNT(1).

    Dry-runs the COUNT query first. Raises if the estimate exceeds 1 GB
    (count queries on our tables should never approach that).

    Args:
        dataset:    BigQuery dataset name (e.g. 'raw')
        table_name: Table name (e.g. 'understat_matches')

    Returns:
        Row count as int.

    Raises:
        ValueError: if dry-run estimate > 1 GB or if table does not exist.
    """
    sql = (
        f"SELECT COUNT(1) AS n "
        f"FROM `{GCP_PROJECT_ID}.{dataset}.{table_name}`"
    )

    client = _get_client()

    # Tighter safety check for COUNT — 1 GB ceiling
    dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_job = client.query(sql, job_config=dry_config)
    estimated_gb = dry_job.total_bytes_processed / 1e9
    logger.info(
        f"get_row_count({dataset}.{table_name}): estimated {estimated_gb:.3f} GB"
    )

    if estimated_gb > _COUNT_QUERY_LIMIT_GB:
        raise ValueError(
            f"COUNT query on {dataset}.{table_name} would scan {estimated_gb:.1f} GB — "
            f"exceeds {_COUNT_QUERY_LIMIT_GB} GB limit. Aborting."
        )

    job = client.query(sql)
    rows = list(job.result())
    count = int(rows[0]["n"])
    logger.info(f"{dataset}.{table_name}: {count:,} rows")
    return count


def _rows_exist(bq_table_id: str, league: str, season: str) -> bool:
    """
    Return True if any rows exist in bq_table_id for the given league+season.

    Uses a partition-filtered COUNT — costs near-zero bytes.
    Returns False if the table does not exist yet.
    """
    client = _get_client()
    sql = (
        f"SELECT COUNT(1) AS n FROM `{bq_table_id}` "
        f"WHERE league = '{league}' AND season = '{season}'"
    )
    dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        dry_job = client.query(sql, job_config=dry_config)
        estimated_gb = dry_job.total_bytes_processed / 1e9
        logger.info(
            f"Existence check dry-run ({bq_table_id} "
            f"league={league} season={season}): {estimated_gb:.4f} GB"
        )
        job = client.query(sql)
        rows = list(job.result())
        return int(rows[0]["n"]) > 0
    except Exception:
        # Table does not exist yet → treat as empty
        return False


def _delete_league_season(bq_table_id: str, league: str, season: str) -> None:
    """
    Delete all rows for the given league+season from bq_table_id.

    Used before a re-load when overwrite=True, to keep the table idempotent.
    """
    client = _get_client()
    sql = (
        f"DELETE FROM `{bq_table_id}` "
        f"WHERE league = '{league}' AND season = '{season}'"
    )
    logger.info(
        f"Deleting existing rows from {bq_table_id} "
        f"(league={league}, season={season})"
    )
    job = client.query(sql)
    job.result()
    logger.info("Delete completed")


def load_parquet_from_gcs(
    league: str,
    source: str,
    season: str,
    table: str,
    mode: str = "WRITE_APPEND",
    overwrite: bool = False,
) -> bigquery.LoadJob | None:
    """
    Load a Parquet file from GCS bronze into the BigQuery raw dataset.

    GCS source path: bronze/{league}/{source}/{season}/{table}.parquet
    BigQuery target: raw.{source}_{table}

    Idempotency (mirrors GCS loader overwrite=False behaviour):
    - If overwrite=False (default) and rows already exist for this
      league+season, the load is skipped and None is returned.
    - If overwrite=True and rows already exist, they are deleted first,
      then the file is loaded fresh.

    Args:
        league:    League key (e.g. 'la_liga')
        source:    Source name (e.g. 'understat', 'espn', 'statsbomb')
        season:    Season year string (e.g. '2024')
        table:     Table descriptor (e.g. 'matches', 'events', 'match_summary')
        mode:      'WRITE_APPEND' (default) or 'WRITE_TRUNCATE' (full table overwrite)
        overwrite: If False (default), skip if rows already exist for league+season.
                   If True, delete existing rows then reload.

    Returns:
        Completed BigQuery LoadJob result, or None if skipped.

    Raises:
        ValueError: if mode is not 'WRITE_APPEND' or 'WRITE_TRUNCATE'.
    """
    if mode not in ("WRITE_APPEND", "WRITE_TRUNCATE"):
        raise ValueError(f"Invalid mode '{mode}'. Use 'WRITE_APPEND' or 'WRITE_TRUNCATE'.")

    gcs_uri = f"gs://{GCS_BUCKET_NAME}/bronze/{league}/{source}/{season}/{table}.parquet"
    bq_table_id = f"{GCP_PROJECT_ID}.{BIGQUERY_DATASET_RAW}.{source}_{table}"

    # Idempotency check — mirrors GCS overwrite=False behaviour
    if mode == "WRITE_APPEND":
        exists = _rows_exist(bq_table_id, league, season)
        if exists and not overwrite:
            logger.info(
                f"Skipping BQ load — rows already exist: "
                f"{bq_table_id} (league={league}, season={season})"
            )
            return None
        if exists and overwrite:
            _delete_league_season(bq_table_id, league, season)

    write_disposition = (
        bigquery.WriteDisposition.WRITE_TRUNCATE
        if mode == "WRITE_TRUNCATE"
        else bigquery.WriteDisposition.WRITE_APPEND
    )

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=write_disposition,
        autodetect=True,
    )

    logger.info(f"Loading {gcs_uri} → {bq_table_id} (mode={mode})")

    client = _get_client()
    job = client.load_table_from_uri(gcs_uri, bq_table_id, job_config=job_config)
    result = job.result()  # waits for completion

    logger.info(f"Loaded {result.output_rows:,} rows → {bq_table_id}")
    return result


def load_multiple(uploads: list[dict]) -> list:
    """
    Load multiple Parquet files from GCS into BigQuery in one call.

    Each item in uploads must be a dict with keys:
        league, source, season, table
    Optionally: mode (str, default 'WRITE_APPEND')

    Per-item errors are logged and collected; the batch continues.
    A summary of failures is logged at the end.

    Example:
        load_multiple([
            {"league": "la_liga", "source": "understat", "season": "2024", "table": "matches"},
            {"league": "la_liga", "source": "espn",      "season": "2024", "table": "lineups"},
        ])

    Returns:
        List of completed LoadJob results for successful items.
    """
    results = []
    failed = []

    for item in uploads:
        try:
            result = load_parquet_from_gcs(
                league=item["league"],
                source=item["source"],
                season=item["season"],
                table=item["table"],
                mode=item.get("mode", "WRITE_APPEND"),
                overwrite=item.get("overwrite", False),
            )
            results.append(result)
        except Exception as e:
            logger.error(
                f"Failed to load {item.get('league')}/{item.get('source')}/"
                f"{item.get('season')}/{item.get('table')}: {e}"
            )
            failed.append(item)

    if failed:
        logger.warning(f"{len(failed)} load(s) failed out of {len(uploads)}")
    else:
        logger.info(f"All {len(uploads)} loads completed successfully")

    return results
