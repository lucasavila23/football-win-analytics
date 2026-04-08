# =============================================================================
# ESPN SCRAPER — SMOKE TESTS
# =============================================================================
# Uses Bundesliga 2023 — cached from validation run, fast to load.
# Tests schema, normalisation, and content — not GCS uploads.
#
# NOTE: saves column is expected to be 89-90% null (goalkeepers only).
# This is not a data quality issue.
# =============================================================================

import pandas as pd
from pipeline.scrapers.espn_scraper import scrape_espn_league_season

LEAGUE = "bundesliga"
SEASON = "2023"

EXPECTED_COLS = {
    "player_name",
    "team",
    "position",
    "fouls_committed",
    "fouls_suffered",
    "saves",
    "league",
    "season",
}


def test_returns_dataframe():
    print("\nTEST 1 — scrape_espn_league_season returns non-empty DataFrame")
    df = scrape_espn_league_season(LEAGUE, SEASON)

    assert df is not None, "lineups is None"
    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert len(df) > 0, "lineups DataFrame is empty"

    print(f"   PASS → {len(df)} rows, {len(df.columns)} columns")


def test_schema():
    print("\nTEST 2 — lineups DataFrame has all required columns")
    df = scrape_espn_league_season(LEAGUE, SEASON)

    missing = EXPECTED_COLS - set(df.columns)
    assert not missing, f"Missing columns: {missing}"

    assert (df["league"] == LEAGUE).all(), "league column wrong"
    assert (df["season"] == SEASON).all(), "season column wrong"

    print(f"   PASS → columns: {sorted(df.columns.tolist())}")


def test_team_names_normalised():
    print("\nTEST 3 — Team names are normalised (lowercase, corrections applied)")
    df = scrape_espn_league_season(LEAGUE, SEASON)

    assert df["team"].str.islower().all(), \
        f"Non-lowercase team names: {df['team'].unique()}"

    all_teams = set(df["team"].unique())

    # Bundesliga: ESPN uses "1. FC Heidenheim 1846" — must become "heidenheim"
    assert "heidenheim" in all_teams, \
        "'heidenheim' not found — 1. FC Heidenheim 1846 correction not applied"
    assert "1. fc heidenheim 1846" not in all_teams, \
        "Raw '1. fc heidenheim 1846' still present"

    # ESPN uses "RB Leipzig" — must stay "rb leipzig"
    assert "rb leipzig" in all_teams, "'rb leipzig' not found"

    # ESPN uses "Borussia Mönchengladbach" — must become "borussia mgladbach"
    assert "borussia mgladbach" in all_teams, \
        "'borussia mgladbach' not found — Mönchengladbach correction not applied"

    print(f"   PASS → sample teams: {sorted(all_teams)[:5]}")


def test_row_count_plausible():
    print("\nTEST 4 — Row count is plausible for Bundesliga 2023")
    df = scrape_espn_league_season(LEAGUE, SEASON)
    # Bundesliga 2023: 306 matches × ~40 rows (starters + subs both teams) ≈ 12,000
    assert len(df) > 5000, f"Too few rows: {len(df)} (expected >5000)"
    assert len(df) < 20000, f"Too many rows: {len(df)}"
    print(f"   PASS → {len(df)} rows")


def test_saves_null_rate():
    print("\nTEST 5 — saves column is 89-90% null (goalkeepers only — expected)")
    df = scrape_espn_league_season(LEAGUE, SEASON)

    if "saves" in df.columns:
        null_rate = df["saves"].isna().mean() * 100
        assert null_rate > 80, \
            f"saves null rate unexpectedly low: {null_rate:.1f}% (expected >80%)"
        print(f"   PASS → saves null rate: {null_rate:.1f}% (expected 89-90%)")
    else:
        print("   SKIP → saves column not present in this dataset")


def test_unsupported_league_returns_none():
    print("\nTEST 6 — Unsupported league returns None gracefully")
    result = scrape_espn_league_season("champions_league", "2023")
    assert result is None, f"Expected None, got {type(result)}"
    print("   PASS → None returned without raising")


if __name__ == "__main__":
    print("=" * 60)
    print("  ESPN SCRAPER SMOKE TESTS")
    print("=" * 60)

    test_returns_dataframe()
    test_schema()
    test_team_names_normalised()
    test_row_count_plausible()
    test_saves_null_rate()
    test_unsupported_league_returns_none()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
