# =============================================================================
# UNDERSTAT SCRAPER
# =============================================================================
# Fetches match-level and player-level xG data from Understat via soccerdata.
#
# Two public functions:
#   scrape_understat(leagues, seasons) → dict of DataFrames, uploaded to GCS
#   scrape_understat_league_season(league, season) → (matches_df, players_df)
#
# Output tables per league/season:
#   matches     — one row per match (xG, PPDA, deep completions, NP xG, etc.)
#   player_stats — one row per player-match appearance
#
# All team name columns are normalised via normalize_name() before return.
# league and season columns are always added (never used as table names).
#
# GCS blob paths:
#   bronze/{league}/understat/{season}/matches.parquet
#   bronze/{league}/understat/{season}/player_stats.parquet
#
# Parallel execution: ThreadPoolExecutor(max_workers=5), one thread per league.
# Timeouts: matches 30s per league, player_stats 600s per league.
# =============================================================================

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import soccerdata as sd
from dotenv import load_dotenv

from pipeline.config import LEAGUES, SOURCES
from pipeline.loaders.gcs_loader import upload_multiple
from pipeline.utils import normalize_name

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Timeouts in seconds
_MATCH_TIMEOUT  = 30
_PLAYER_TIMEOUT = 600

# soccerdata league IDs for Understat-covered leagues (all except UCL)
_UNDERSTAT_LEAGUES = {
    lk: lid for lk, lid in LEAGUES.items()
    if lk in SOURCES["understat"]
}

# Understat bonus columns captured beyond the minimum required
_MATCH_KEEP_COLS = [
    "date", "home_team", "away_team",
    "home_goals", "away_goals",
    "home_xg", "away_xg",
    "home_ppda", "away_ppda",
    "home_np_xg", "away_np_xg",
    "home_deep", "away_deep",
]

_PLAYER_KEEP_COLS = [
    "player", "team",
    "minutes", "goals", "assists", "shots",
    "xg", "xa", "xg_chain", "xg_buildup",
    "key_passes", "yellow_cards", "red_cards",
    "own_goals", "position", "position_id",
]


def _fetch_matches(league_id: str) -> pd.DataFrame:
    """Fetch Understat team match stats for the configured season(s)."""
    df = sd.Understat(leagues=league_id).read_team_match_stats()
    return df.reset_index()


def _fetch_players(league_id: str) -> pd.DataFrame:
    """Fetch Understat player match stats for the configured season(s)."""
    df = sd.Understat(leagues=league_id).read_player_match_stats()
    return df.reset_index()


def _normalise_matches(raw: pd.DataFrame, league_key: str, season: str) -> pd.DataFrame:
    """
    Clean and normalise a raw Understat matches DataFrame.

    Renames columns to the pipeline schema, strips accents from team names,
    adds league/season, and selects only the columns we store.
    """
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]

    # Rename soccerdata column names → our schema
    rename = {
        "home_goals": "home_score",
        "away_goals":  "away_score",
        "home_deep":   "home_deep_completions",
        "away_deep":   "away_deep_completions",
    }
    df = df.rename(columns=rename)

    # Normalise team names
    for col in ["home_team", "away_team"]:
        if col in df.columns:
            df[col] = df[col].apply(normalize_name)

    # Normalise date to YYYY-MM-DD string
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # Add pipeline identity columns
    df["league"] = league_key
    df["season"] = season

    # Select output columns in canonical order (drop missing gracefully)
    output_cols = [
        "date", "home_team", "away_team",
        "home_score", "away_score",
        "home_xg", "away_xg",
        "home_ppda", "away_ppda",
        "home_np_xg", "away_np_xg",
        "home_deep_completions", "away_deep_completions",
        "league", "season",
    ]
    present = [c for c in output_cols if c in df.columns]
    return df[present]


def _normalise_players(raw: pd.DataFrame, league_key: str, season: str) -> pd.DataFrame:
    """
    Clean and normalise a raw Understat player_match_stats DataFrame.

    Renames columns to the pipeline schema, normalises team names,
    adds league/season, and selects only the columns we store.
    """
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]

    # Rename soccerdata column → our schema
    rename = {
        "player":       "player_name",
        "yellow_cards": "yellow_card",
        "red_cards":    "red_card",
    }
    df = df.rename(columns=rename)

    # Normalise team names
    if "team" in df.columns:
        df["team"] = df["team"].apply(normalize_name)

    # Add pipeline identity columns
    df["league"] = league_key
    df["season"] = season

    # Select output columns in canonical order
    output_cols = [
        "player_name", "team",
        "minutes", "goals", "assists", "shots",
        "xg", "xa", "xg_chain", "xg_buildup",
        "key_passes", "yellow_card", "red_card",
        "own_goals", "position", "position_id",
        "league", "season",
    ]
    present = [c for c in output_cols if c in df.columns]
    return df[present]


def scrape_understat_league_season(
    league_key: str,
    season: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """
    Fetch Understat data for a single league + season.

    Args:
        league_key: League key from config (e.g. 'la_liga')
        season:     Season start year as string (e.g. '2023')

    Returns:
        (matches_df, players_df) — both normalised and schema-aligned.
        Either may be None if the fetch fails or the league is unsupported.
    """
    if league_key not in _UNDERSTAT_LEAGUES:
        logger.warning(f"Understat: unsupported league '{league_key}' — skipping")
        return None, None

    league_id = _UNDERSTAT_LEAGUES[league_key]
    logger.info(f"Understat: fetching {league_key}/{season} ({league_id})")

    # --- Matches ---
    matches_df = None
    t0 = time.time()
    try:
        ud = sd.Understat(leagues=league_id, seasons=season)
        raw_matches = ud.read_team_match_stats().reset_index()
        matches_df = _normalise_matches(raw_matches, league_key, season)
        logger.info(
            f"Understat matches: {league_key}/{season} — {len(matches_df)} rows "
            f"in {time.time()-t0:.1f}s"
        )
    except Exception as e:
        logger.error(f"Understat matches fetch failed ({league_key}/{season}): {e}")

    # --- Players ---
    players_df = None
    t0 = time.time()
    try:
        ud = sd.Understat(leagues=league_id, seasons=season)
        raw_players = ud.read_player_match_stats().reset_index()
        players_df = _normalise_players(raw_players, league_key, season)
        logger.info(
            f"Understat players: {league_key}/{season} — {len(players_df)} rows "
            f"in {time.time()-t0:.1f}s"
        )
    except Exception as e:
        logger.error(f"Understat players fetch failed ({league_key}/{season}): {e}")

    return matches_df, players_df


def scrape_understat(
    leagues: list[str] | None = None,
    seasons: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, list[str]]:
    """
    Scrape Understat for the given leagues and seasons, upload to GCS.

    Fetches all leagues in parallel (ThreadPoolExecutor, max_workers=5).
    Uploads via upload_multiple() — never in a per-match loop.

    Args:
        leagues:   League keys to scrape. Defaults to all in SOURCES['understat'].
        seasons:   Season years to scrape (e.g. ['2023', '2024']).
                   Defaults to current season from config.
        overwrite: If False (default), skip GCS blobs that already exist.

    Returns:
        Dict mapping league_key → list of GCS URIs uploaded.
    """
    from pipeline.config import CURRENT_SEASON

    target_leagues = leagues or SOURCES["understat"]
    target_seasons = seasons or [CURRENT_SEASON]

    all_uris: dict[str, list[str]] = {}

    for season in target_seasons:
        logger.info(
            f"Understat: season {season} — "
            f"fetching {len(target_leagues)} leagues in parallel"
        )

        # Build task list using closure pattern to capture loop variable
        tasks = {
            lk: (lambda lid, lk=lk: scrape_understat_league_season(lk, season))
            for lk in target_leagues
            if lk in _UNDERSTAT_LEAGUES
        }

        results: dict[str, tuple] = {}

        with ThreadPoolExecutor(max_workers=5) as pool:
            future_to_league = {
                pool.submit(fn): lk for lk, fn in tasks.items()
            }
            for future in as_completed(future_to_league):
                lk = future_to_league[future]
                try:
                    results[lk] = future.result(timeout=_PLAYER_TIMEOUT)
                except Exception as e:
                    logger.error(f"Understat thread failed ({lk}/{season}): {e}")
                    results[lk] = (None, None)

        # Batch-upload all results for this season
        uploads = []
        for lk, (matches_df, players_df) in results.items():
            if matches_df is not None and not matches_df.empty:
                uploads.append({
                    "df":       matches_df,
                    "league":   lk,
                    "source":   "understat",
                    "season":   season,
                    "table":    "matches",
                    "overwrite": overwrite,
                })
            if players_df is not None and not players_df.empty:
                uploads.append({
                    "df":       players_df,
                    "league":   lk,
                    "source":   "understat",
                    "season":   season,
                    "table":    "player_stats",
                    "overwrite": overwrite,
                })

        if uploads:
            uris = upload_multiple(uploads)
            for item, uri in zip(uploads, uris):
                all_uris.setdefault(item["league"], []).append(uri)
        else:
            logger.warning(f"Understat: no data to upload for season {season}")

    return all_uris
