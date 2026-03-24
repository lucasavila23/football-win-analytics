# =============================================================================
# GCS LOADER — SMOKE TESTS
# =============================================================================
# Tests the four core functions of the GCS loader:
#   1. upload_dataframe   — single upload
#   2. upload_multiple    — batch upload
#   3. list_blobs         — listing with filters
#   4. download_dataframe — round-trip check
# =============================================================================

import pandas as pd
from pipeline.loaders.gcs_loader import (
    upload_dataframe,
    upload_multiple,
    list_blobs,
    download_dataframe
)

# ── Test data ──────────────────────────────────────────────────────────────────
LEAGUE  = "la_liga"
SOURCE  = "test"
SEASON  = "9999"          # Fake season so test data never mixes with real data
TABLE_A = "matches"
TABLE_B = "player_stats"

sample_matches = pd.DataFrame({
    "date":       ["2024-08-10", "2024-08-11"],
    "home_team":  ["Real Madrid", "Barcelona"],
    "away_team":  ["Atletico Madrid", "Sevilla"],
    "home_score": [2, 1],
    "away_score": [0, 1],
    "home_xg":    [1.85, 0.92],
    "away_xg":    [0.43, 0.88],
    "season":     ["2024", "2024"],
    "league":     ["la_liga", "la_liga"]
})

sample_players = pd.DataFrame({
    "player_name": ["Vinicius Jr", "Bellingham"],
    "team":        ["Real Madrid", "Real Madrid"],
    "goals":       [1, 1],
    "xg":          [0.72, 0.55],
    "xg_chain":    [1.10, 0.90],
    "season":      ["2024", "2024"],
    "league":      ["la_liga", "la_liga"]
})


def test_single_upload():
    print("\nTEST 1 — Single upload")
    uri = upload_dataframe(sample_matches, LEAGUE, SOURCE, SEASON, TABLE_A)
    assert uri.startswith("gs://"), f"Expected GCS URI, got: {uri}"
    print(f"   PASS → {uri}")


def test_batch_upload():
    print("\nTEST 2 — Batch upload")
    uris = upload_multiple([
        {"df": sample_matches, "league": LEAGUE, "source": SOURCE, "season": SEASON, "table": TABLE_A},
        {"df": sample_players, "league": LEAGUE, "source": SOURCE, "season": SEASON, "table": TABLE_B},
    ])
    assert len(uris) == 2, f"Expected 2 URIs, got {len(uris)}"
    print(f"   PASS → {len(uris)} files uploaded")


def test_list_blobs():
    print("\nTEST 3 — List blobs")
    blobs = list_blobs(league=LEAGUE, source=SOURCE, season=SEASON)
    assert len(blobs) >= 2, f"Expected at least 2 blobs, found {len(blobs)}"
    print(f"   PASS → Found {len(blobs)} blobs:")
    for b in blobs:
        print(f"          {b}")


def test_download_roundtrip():
    print("\nTEST 4 — Download round-trip")
    df = download_dataframe(LEAGUE, SOURCE, SEASON, TABLE_A)
    assert len(df) == len(sample_matches), \
        f"Row count mismatch: expected {len(sample_matches)}, got {len(df)}"
    assert list(df.columns) == list(sample_matches.columns), \
        "Column mismatch after round-trip"
    print(f"   PASS → {len(df)} rows downloaded, schema intact")


def test_overwrite_false():
    print("\nTEST 5 — Skip existing blob (overwrite=False)")
    uri = upload_dataframe(
        sample_matches, LEAGUE, SOURCE, SEASON, TABLE_A, overwrite=False
    )
    print(f"   PASS → Correctly skipped existing blob")


def test_empty_dataframe():
    print("\nTEST 6 — Empty DataFrame raises ValueError")
    try:
        upload_dataframe(pd.DataFrame(), LEAGUE, SOURCE, SEASON, "empty")
        print("   FAIL → Should have raised ValueError")
    except ValueError as e:
        print(f"   PASS → Correctly raised ValueError: {e}")


if __name__ == "__main__":
    print("=" * 55)
    print("  GCS LOADER SMOKE TESTS")
    print("=" * 55)

    test_single_upload()
    test_batch_upload()
    test_list_blobs()
    test_download_roundtrip()
    test_overwrite_false()
    test_empty_dataframe()

    print("\n" + "=" * 55)
    print("  ALL TESTS PASSED")
    print("=" * 55)