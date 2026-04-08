# =============================================================================
# UNDERSTAT SCRAPER — SMOKE TESTS
# =============================================================================
# Uses Bundesliga 2023 — cached from validation run, fast to load.
# Tests schema, normalisation, and content — not GCS uploads.
# =============================================================================

import pandas as pd
from pipeline.scrapers.understat_scraper import scrape_understat_league_season

LEAGUE = "bundesliga"
SEASON = "2023"

EXPECTED_MATCH_COLS = {
    "date", "home_team", "away_team",
    "home_score", "away_score",
    "home_xg", "away_xg",
    "league", "season",
}

EXPECTED_PLAYER_COLS = {
    "player_name", "team",
    "minutes", "goals", "xg", "xa",
    "xg_chain", "xg_buildup",
    "league", "season",
}


def test_returns_dataframes():
    print("\nTEST 1 — scrape_understat_league_season returns non-empty DataFrames")
    matches, players = scrape_understat_league_season(LEAGUE, SEASON)

    assert matches is not None, "matches is None"
    assert players is not None, "players is None"
    assert isinstance(matches, pd.DataFrame), f"matches is not DataFrame: {type(matches)}"
    assert isinstance(players, pd.DataFrame), f"players is not DataFrame: {type(players)}"
    assert len(matches) > 0, "matches is empty"
    assert len(players) > 0, "players is empty"

    print(f"   PASS → matches={len(matches)} rows, players={len(players)} rows")


def test_matches_schema():
    print("\nTEST 2 — matches DataFrame has all required columns")
    matches, _ = scrape_understat_league_season(LEAGUE, SEASON)

    missing = EXPECTED_MATCH_COLS - set(matches.columns)
    assert not missing, f"Missing match columns: {missing}"

    assert (matches["league"] == LEAGUE).all(), "league column wrong"
    assert (matches["season"] == SEASON).all(), "season column wrong"

    print(f"   PASS → columns: {sorted(matches.columns.tolist())}")


def test_players_schema():
    print("\nTEST 3 — player_stats DataFrame has all required columns")
    _, players = scrape_understat_league_season(LEAGUE, SEASON)

    missing = EXPECTED_PLAYER_COLS - set(players.columns)
    assert not missing, f"Missing player columns: {missing}"

    assert (players["league"] == LEAGUE).all(), "league column wrong"
    assert (players["season"] == SEASON).all(), "season column wrong"

    print(f"   PASS → columns: {sorted(players.columns.tolist())}")


def test_team_names_normalised():
    print("\nTEST 4 — Team names are normalised (lowercase, no accents, corrections applied)")
    matches, players = scrape_understat_league_season(LEAGUE, SEASON)

    # After normalisation all team names should be lowercase
    for col in ["home_team", "away_team"]:
        assert matches[col].str.islower().all(), \
            f"{col} contains non-lowercase values: {matches[col].unique()}"

    assert players["team"].str.islower().all(), \
        f"team contains non-lowercase values: {players['team'].unique()}"

    # Specific known corrections for Bundesliga
    all_teams = set(matches["home_team"]) | set(matches["away_team"])
    assert "rb leipzig" in all_teams, \
        "'rb leipzig' not found — RasenBallsport Leipzig correction not applied"
    assert "rasenballsport leipzig" not in all_teams, \
        "Raw 'rasenballsport leipzig' still present"

    print(f"   PASS → sample teams: {sorted(all_teams)[:5]}")


def test_match_count():
    print("\nTEST 5 — Bundesliga 2023 has expected ~306 matches")
    matches, _ = scrape_understat_league_season(LEAGUE, SEASON)
    # Bundesliga has 18 teams × 34 matchdays = 306 matches
    assert len(matches) == 306, f"Expected 306 matches, got {len(matches)}"
    print(f"   PASS → {len(matches)} matches")


def test_xg_values_plausible():
    print("\nTEST 6 — xG values are non-negative and plausible")
    matches, players = scrape_understat_league_season(LEAGUE, SEASON)

    assert (matches["home_xg"] >= 0).all(), "Negative home_xg"
    assert (matches["away_xg"] >= 0).all(), "Negative away_xg"
    assert matches["home_xg"].max() < 10, f"Implausibly high home_xg: {matches['home_xg'].max()}"

    assert (players["xg"] >= 0).all(), "Negative player xg"
    assert (players["minutes"] >= 0).all(), "Negative minutes"

    print(f"   PASS → avg home_xg={matches['home_xg'].mean():.2f}, "
          f"max player xg={players['xg'].max():.2f}")


def test_unsupported_league_returns_none():
    print("\nTEST 7 — Unsupported league returns (None, None) gracefully")
    matches, players = scrape_understat_league_season("champions_league", "2023")
    assert matches is None, f"Expected None for matches, got {type(matches)}"
    assert players is None, f"Expected None for players, got {type(players)}"
    print("   PASS → (None, None) returned without raising")


if __name__ == "__main__":
    print("=" * 60)
    print("  UNDERSTAT SCRAPER SMOKE TESTS")
    print("=" * 60)

    test_returns_dataframes()
    test_matches_schema()
    test_players_schema()
    test_team_names_normalised()
    test_match_count()
    test_xg_values_plausible()
    test_unsupported_league_returns_none()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
