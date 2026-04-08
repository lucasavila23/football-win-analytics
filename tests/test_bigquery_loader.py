# =============================================================================
# BIGQUERY LOADER — SMOKE TESTS
# =============================================================================
# Tests the five core functions of the BigQuery loader.
#
# Tests 1–3 are logic-only (no GCP calls):
#   1. table_exists()           — returns bool
#   2. run_query() dry-run      — returns float (estimated GB)
#   3. run_query() limit check  — raises ValueError above 10 GB
#
# Tests 4–5 require live GCP credentials:
#   4. load_parquet_from_gcs()  — upload test DataFrame to GCS, load to BQ
#   5. load_multiple()          — one valid + one invalid item, partial failure
#
# Uses source="test", season="9999" to isolate test data from real tables.
# =============================================================================

import pandas as pd
from unittest.mock import MagicMock, patch

from pipeline.loaders.bigquery_loader import (
    table_exists,
    run_query,
    load_parquet_from_gcs,
    load_multiple,
)
from pipeline.loaders.gcs_loader import upload_dataframe

LEAGUE  = "la_liga"
SOURCE  = "test"
SEASON  = "9999"
TABLE   = "matches"

sample_df = pd.DataFrame({
    "date":       ["2024-08-10", "2024-08-11"],
    "home_team":  ["Real Madrid", "Barcelona"],
    "away_team":  ["Atletico Madrid", "Sevilla"],
    "home_score": [2, 1],
    "away_score": [0, 1],
    "season":     [SEASON, SEASON],
    "league":     [LEAGUE, LEAGUE],
})


# =============================================================================
# Tests 1–3: logic-only (mock BigQuery client)
# =============================================================================

def test_table_exists_returns_bool():
    print("\nTEST 1 — table_exists() returns a bool (live GCP check)")
    result = table_exists("raw", "test_matches")
    assert isinstance(result, bool), f"Expected bool, got {type(result)}"
    print(f"   PASS → table_exists('raw', 'test_matches') = {result}")


def test_run_query_dry_run_returns_float():
    print("\nTEST 2 — run_query(dry_run=True) returns estimated GB as float")
    # SELECT 1 scans 0 bytes — safe and fast
    result = run_query("SELECT 1", dry_run=True)
    assert isinstance(result, float), f"Expected float, got {type(result)}"
    assert result >= 0.0, f"Estimated GB should be >= 0, got {result}"
    print(f"   PASS → Estimated GB for SELECT 1: {result:.3f}")


def test_run_query_raises_on_large_estimate():
    print("\nTEST 3 — run_query() raises ValueError when estimate > 10 GB")

    # Patch _get_client to return a mock whose dry-run job reports > 10 GB
    mock_dry_job = MagicMock()
    mock_dry_job.total_bytes_processed = int(11 * 1e9)  # 11 GB

    mock_client = MagicMock()
    mock_client.query.return_value = mock_dry_job

    with patch("pipeline.loaders.bigquery_loader._get_client", return_value=mock_client):
        try:
            run_query("SELECT * FROM `some.big.table`", dry_run=False)
            print("   FAIL → Should have raised ValueError")
            assert False, "Expected ValueError was not raised"
        except ValueError as e:
            assert "10 GB" in str(e) or "safety limit" in str(e), \
                f"Error message doesn't mention limit: {e}"
            print(f"   PASS → Correctly raised ValueError: {e}")


# =============================================================================
# Tests 4–5: live GCP (require GOOGLE_APPLICATION_CREDENTIALS)
# =============================================================================

def test_load_parquet_from_gcs():
    print("\nTEST 4 — load_parquet_from_gcs() (live GCP: GCS upload + BQ load)")

    # First write the test file to GCS so BQ has something to load
    uri = upload_dataframe(sample_df, LEAGUE, SOURCE, SEASON, TABLE, overwrite=True)
    print(f"   GCS upload → {uri}")

    # Load from GCS into BigQuery raw.test_matches
    result = load_parquet_from_gcs(LEAGUE, SOURCE, SEASON, TABLE, mode="WRITE_TRUNCATE")

    assert result is not None, "Expected a LoadJob result"
    assert result.output_rows == len(sample_df), \
        f"Expected {len(sample_df)} rows loaded, got {result.output_rows}"

    print(f"   PASS → Loaded {result.output_rows} rows into raw.{SOURCE}_{TABLE}")


def test_load_multiple_partial_failure():
    print("\nTEST 5 — load_multiple() with one valid and one bad item")

    uploads = [
        # Valid: test file already in GCS from test 4
        {"league": LEAGUE, "source": SOURCE, "season": SEASON, "table": TABLE, "mode": "WRITE_TRUNCATE"},
        # Invalid: GCS path does not exist
        {"league": LEAGUE, "source": SOURCE, "season": "0000", "table": "nonexistent"},
    ]

    results = load_multiple(uploads)

    assert len(results) == 1, \
        f"Expected 1 successful result, got {len(results)}"
    print(f"   PASS → 1 succeeded, 1 failed (failure logged, batch did not abort)")


if __name__ == "__main__":
    print("=" * 60)
    print("  BIGQUERY LOADER SMOKE TESTS")
    print("=" * 60)

    test_table_exists_returns_bool()
    test_run_query_dry_run_returns_float()
    test_run_query_raises_on_large_estimate()
    test_load_parquet_from_gcs()
    test_load_multiple_partial_failure()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
