# =============================================================================
# GCS LOADER
# =============================================================================
# Responsibility: Take a DataFrame from any scraper and write it to the
# correct location in the GCS Bronze bucket as a Parquet file.
#
# Naming convention for blobs:
#   bronze/{league}/{source}/{season}/data.parquet
#
# Example:
#   bronze/la_liga/understat/2024/data.parquet
#   bronze/premier_league/espn/2024/data.parquet
# =============================================================================

import io
import logging
from datetime import datetime
from dotenv import load_dotenv
from google.cloud import storage
import pandas as pd

from pipeline.config import GCS_BUCKET_NAME, GCP_PROJECT_ID

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def _build_blob_path(league: str, source: str, season: str, table: str) -> str:
    """
    Build the full GCS blob path for a given dataset.

    Args:
        league:  League key from config (e.g. 'la_liga')
        source:  Data source name (e.g. 'understat', 'espn', 'fbref')
        season:  Season year as string (e.g. '2024')
        table:   Table name describing the data (e.g. 'matches', 'player_stats', 'lineups')

    Returns:
        Full blob path string e.g. 'bronze/la_liga/understat/2024/matches.parquet'
    """
    return f"bronze/{league}/{source}/{season}/{table}.parquet"


def upload_dataframe(
    df: pd.DataFrame,
    league: str,
    source: str,
    season: str,
    table: str,
    overwrite: bool = True
) -> str:
    """
    Upload a DataFrame to GCS as a Parquet file.

    Args:
        df:        The DataFrame to upload
        league:    League key (e.g. 'la_liga')
        source:    Source name (e.g. 'understat')
        season:    Season year (e.g. '2024')
        table:     Table descriptor (e.g. 'matches')
        overwrite: If False, skip upload if blob already exists

    Returns:
        The full GCS URI of the uploaded file (gs://bucket/path)

    Raises:
        ValueError: If the DataFrame is empty
        Exception:  If the GCS upload fails
    """
    if df.empty:
        raise ValueError(
            f"DataFrame is empty — nothing to upload "
            f"({league}/{source}/{season}/{table})"
        )

    blob_path = _build_blob_path(league, source, season, table)
    gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"

    # Connect to GCS
    client = storage.Client(project=GCP_PROJECT_ID)
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_path)

    # Skip if exists and overwrite is off
    if not overwrite and blob.exists():
        logger.info(f"Skipping — blob already exists: {gcs_uri}")
        return gcs_uri

    # Serialise DataFrame to Parquet in memory (no temp files on disk)
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    # Upload
    blob.upload_from_file(buffer, content_type="application/octet-stream")

    logger.info(
        f"Uploaded {len(df)} rows → {gcs_uri} "
        f"({buffer.tell() / 1024:.1f} KB)"
    )

    return gcs_uri


def upload_multiple(uploads: list[dict]) -> list[str]:
    """
    Upload multiple DataFrames in one call.

    Each item in uploads must be a dict with keys:
        df, league, source, season, table
    Optionally: overwrite (bool, default True)

    Example:
        upload_multiple([
            {"df": matches_df,  "league": "la_liga", "source": "understat", "season": "2024", "table": "matches"},
            {"df": players_df,  "league": "la_liga", "source": "understat", "season": "2024", "table": "player_stats"},
            {"df": lineups_df,  "league": "la_liga", "source": "espn",      "season": "2024", "table": "lineups"},
        ])

    Returns:
        List of GCS URIs for all uploaded files
    """
    uris = []
    failed = []

    for item in uploads:
        try:
            uri = upload_dataframe(
                df=item["df"],
                league=item["league"],
                source=item["source"],
                season=item["season"],
                table=item["table"],
                overwrite=item.get("overwrite", True)
            )
            uris.append(uri)
        except Exception as e:
            logger.error(
                f"Failed to upload {item.get('league')}/{item.get('source')}/"
                f"{item.get('season')}/{item.get('table')}: {e}"
            )
            failed.append(item)

    if failed:
        logger.warning(f"{len(failed)} upload(s) failed out of {len(uploads)}")
    else:
        logger.info(f"All {len(uploads)} uploads completed successfully")

    return uris


def list_blobs(league: str = None, source: str = None, season: str = None) -> list[str]:
    """
    List blobs in the bronze bucket, optionally filtered.

    Args:
        league:  Filter by league (optional)
        source:  Filter by source (optional)
        season:  Filter by season (optional)

    Returns:
        List of blob path strings
    """
    client = storage.Client(project=GCP_PROJECT_ID)
    bucket = client.bucket(GCS_BUCKET_NAME)

    # Build prefix from whatever filters are provided
    prefix = "bronze/"
    if league:
        prefix += f"{league}/"
    if source:
        prefix += f"{source}/"
    if season:
        prefix += f"{season}/"

    blobs = bucket.list_blobs(prefix=prefix)
    paths = [blob.name for blob in blobs if blob.name.endswith(".parquet")]

    return paths


def download_dataframe(
    league: str,
    source: str,
    season: str,
    table: str
) -> pd.DataFrame:
    """
    Download a Parquet file from GCS and return it as a DataFrame.
    Useful for inspection, debugging, or reprocessing.

    Args:
        league:  League key
        source:  Source name
        season:  Season year
        table:   Table descriptor

    Returns:
        DataFrame of the stored data

    Raises:
        FileNotFoundError: If the blob does not exist
    """
    blob_path = _build_blob_path(league, source, season, table)
    gcs_uri = f"gs://{GCS_BUCKET_NAME}/{blob_path}"

    client = storage.Client(project=GCP_PROJECT_ID)
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        raise FileNotFoundError(f"No blob found at: {gcs_uri}")

    buffer = io.BytesIO()
    blob.download_to_file(buffer)
    buffer.seek(0)

    df = pd.read_parquet(buffer, engine="pyarrow")
    logger.info(f"Downloaded {len(df)} rows ← {gcs_uri}")

    return df