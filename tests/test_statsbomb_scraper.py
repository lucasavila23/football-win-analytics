# =============================================================================
# STATSBOMB SCRAPER — SMOKE TESTS
# =============================================================================
# Tests the two public functions of the StatsBomb scraper:
#   1. scrape_events       — raw event DataFrame
#   2. scrape_match_summary — aggregated per-match metrics
#
# Uses La Liga 2015/2016 (competition_id=11, season_id=27) as the live test
# case — it has 380 matches and is the largest freely available season.
# =============================================================================

import pandas as pd

from pipeline.scrapers.statsbomb_scraper import scrape_events, scrape_match_summary

LEAGUE = "la_liga"
SEASON = "2015"  # → 2015/2016

EXPECTED_MATCH_SUMMARY_COLS = {
    "match_id",
    "match_date",
    "home_team",
    "away_team",
    "league",
    "season",
    "home_pressures",
    "away_pressures",
    "home_under_pressure_passes",
    "away_under_pressure_passes",
    "home_progressive_carries",
    "away_progressive_carries",
}


def test_scrape_events_returns_dataframe():
    print("\nTEST 1 — scrape_events returns a non-empty DataFrame with required columns")
    df = scrape_events(LEAGUE, SEASON)

    assert df is not None, "Expected DataFrame, got None"
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert len(df) > 0, "Events DataFrame is empty"

    assert "league" in df.columns, "Missing 'league' column"
    assert "season" in df.columns, "Missing 'season' column"
    assert "type" in df.columns, "Missing 'type' column"

    assert df["league"].iloc[0] == LEAGUE, f"Expected league={LEAGUE}, got {df['league'].iloc[0]}"
    assert df["season"].iloc[0] == SEASON, f"Expected season={SEASON}, got {df['season'].iloc[0]}"

    print(f"   PASS → {len(df)} events, {len(df.columns)} columns")
    print(f"          league={df['league'].iloc[0]}, season={df['season'].iloc[0]}")
    print(f"          Unique event types: {sorted(df['type'].unique())[:10]} ...")


def test_scrape_match_summary_columns():
    print("\nTEST 2 — scrape_match_summary has all required columns and ~380 rows")
    df = scrape_match_summary(LEAGUE, SEASON)

    assert df is not None, "Expected DataFrame, got None"
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"

    missing = EXPECTED_MATCH_SUMMARY_COLS - set(df.columns)
    assert not missing, f"Missing columns in match_summary: {missing}"

    # La Liga 2015/2016 has 380 matches
    assert len(df) >= 370, f"Expected ~380 rows, got {len(df)}"

    print(f"   PASS → {len(df)} matches, all {len(EXPECTED_MATCH_SUMMARY_COLS)} expected columns present")
    print(f"          Columns: {sorted(df.columns.tolist())}")
    print(f"          Sample row:\n{df.iloc[0].to_string()}")


def test_progressive_carries_non_negative():
    print("\nTEST 3 — home_ and away_progressive_carries are all >= 0")
    df = scrape_match_summary(LEAGUE, SEASON)

    assert df is not None, "Expected DataFrame, got None"

    assert (df["home_progressive_carries"] >= 0).all(), \
        "Negative values in home_progressive_carries"
    assert (df["away_progressive_carries"] >= 0).all(), \
        "Negative values in away_progressive_carries"

    home_mean = df["home_progressive_carries"].mean()
    away_mean = df["away_progressive_carries"].mean()
    print(f"   PASS → home avg={home_mean:.1f}, away avg={away_mean:.1f} progressive carries/match")


def test_graceful_skip_missing_season():
    print("\nTEST 4 — scrape_events returns None for uncovered season (no raise)")
    result = scrape_events("la_liga", "1999")

    assert result is None, f"Expected None for uncovered season, got {type(result)}"
    print("   PASS → Correctly returned None without raising")


if __name__ == "__main__":
    print("=" * 60)
    print("  STATSBOMB SCRAPER SMOKE TESTS")
    print("=" * 60)

    test_scrape_events_returns_dataframe()
    test_scrape_match_summary_columns()
    test_progressive_carries_non_negative()
    test_graceful_skip_missing_season()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
