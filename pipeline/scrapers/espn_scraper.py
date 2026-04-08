# =============================================================================
# ESPN SCRAPER
# =============================================================================
# Fetches lineup and player event data from ESPN via soccerdata.
#
# Two public functions:
#   scrape_espn(leagues, seasons)              → uploads to GCS, returns URIs
#   scrape_espn_league_season(league, season)  → lineups_df
#
# Output table per league/season:
#   lineups — one row per player per match appearance
#
# All team name columns are normalised via normalize_name() before return.
# league and season columns are always added (never used as table names).
#
# GCS blob path:
#   bronze/{league}/espn/{season}/lineups.parquet
#
# Parallel execution: ThreadPoolExecutor(max_workers=5), one thread per league.
# Timeout: 600s per league (ESPN makes ~380 individual HTTP requests per league).
#
# NOTE: ESPN `saves` column is 89-90% null — this is correct and expected.
# Only goalkeepers have saves. Do not treat this as a data quality issue.
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

_ESPN_TIMEOUT = 600

_ESPN_LEAGUES = {
    lk: lid for lk, lid in LEAGUES.items()
    if lk in SOURCES["espn"]
}

# Output columns in canonical order (missing columns dropped gracefully)
_LINEUP_OUTPUT_COLS = [
    "player_name",
    "team",
    "is_home",
    "position",
    "formation_place",
    "sub_in",
    "sub_out",
    "shots_on_target",
    "fouls_committed",
    "fouls_suffered",
    "offsides",
    "saves",
    "goals_conceded",
    "shots_faced",
    "goal_assists",
    "league",
    "season",
]


def _normalise_lineups(raw: pd.DataFrame, league_key: str, season: str) -> pd.DataFrame:
    """
    Clean and normalise a raw ESPN lineups DataFrame.

    Renames columns to the pipeline schema, normalises team names,
    derives is_starter from position, adds league/season, and selects
    only the columns we store.
    """
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]

    # Rename soccerdata column → our schema
    rename = {"player": "player_name"}
    df = df.rename(columns=rename)

    # Normalise team names
    if "team" in df.columns:
        df["team"] = df["team"].apply(normalize_name)

    # Add pipeline identity columns
    df["league"] = league_key
    df["season"] = season

    # Select output columns (drop any that are absent from this source)
    present = [c for c in _LINEUP_OUTPUT_COLS if c in df.columns]
    return df[present]


def scrape_espn_league_season(
    league_key: str,
    season: str,
) -> pd.DataFrame | None:
    """
    Fetch ESPN lineup data for a single league + season.

    Args:
        league_key: League key from config (e.g. 'la_liga')
        season:     Season start year as string (e.g. '2023')

    Returns:
        Normalised lineups DataFrame, or None if the league is unsupported
        or the fetch fails.
    """
    if league_key not in _ESPN_LEAGUES:
        logger.warning(f"ESPN: unsupported league '{league_key}' — skipping")
        return None

    league_id = _ESPN_LEAGUES[league_key]
    logger.info(f"ESPN: fetching {league_key}/{season} ({league_id})")

    t0 = time.time()
    try:
        espn = sd.ESPN(leagues=league_id, seasons=season)
        raw = espn.read_lineup().reset_index()
        lineups = _normalise_lineups(raw, league_key, season)
        logger.info(
            f"ESPN lineups: {league_key}/{season} — {len(lineups)} rows "
            f"in {time.time()-t0:.1f}s"
        )
        return lineups
    except Exception as e:
        logger.error(f"ESPN fetch failed ({league_key}/{season}): {e}")
        return None


def scrape_espn(
    leagues: list[str] | None = None,
    seasons: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, list[str]]:
    """
    Scrape ESPN lineups for the given leagues and seasons, upload to GCS.

    Fetches all leagues in parallel (ThreadPoolExecutor, max_workers=5).
    Uploads via upload_multiple() — never in a per-match loop.

    Args:
        leagues:   League keys to scrape. Defaults to all in SOURCES['espn'].
        seasons:   Season years (e.g. ['2023', '2024']).
                   Defaults to current season from config.
        overwrite: If False (default), skip GCS blobs that already exist.

    Returns:
        Dict mapping league_key → list of GCS URIs uploaded.
    """
    from pipeline.config import CURRENT_SEASON

    target_leagues = leagues or SOURCES["espn"]
    target_seasons = seasons or [CURRENT_SEASON]

    all_uris: dict[str, list[str]] = {}

    for season in target_seasons:
        logger.info(
            f"ESPN: season {season} — "
            f"fetching {len(target_leagues)} leagues in parallel"
        )

        # Closure pattern: capture lk at definition time to avoid late-binding
        tasks = {
            lk: (lambda lk=lk: scrape_espn_league_season(lk, season))
            for lk in target_leagues
            if lk in _ESPN_LEAGUES
        }

        results: dict[str, pd.DataFrame | None] = {}

        with ThreadPoolExecutor(max_workers=5) as pool:
            future_to_league = {
                pool.submit(fn): lk for lk, fn in tasks.items()
            }
            for future in as_completed(future_to_league):
                lk = future_to_league[future]
                try:
                    results[lk] = future.result(timeout=_ESPN_TIMEOUT)
                except Exception as e:
                    logger.error(f"ESPN thread failed ({lk}/{season}): {e}")
                    results[lk] = None

        # Batch-upload all results for this season
        uploads = []
        for lk, lineups_df in results.items():
            if lineups_df is not None and not lineups_df.empty:
                uploads.append({
                    "df":       lineups_df,
                    "league":   lk,
                    "source":   "espn",
                    "season":   season,
                    "table":    "lineups",
                    "overwrite": overwrite,
                })

        if uploads:
            uris = upload_multiple(uploads)
            for item, uri in zip(uploads, uris):
                all_uris.setdefault(item["league"], []).append(uri)
        else:
            logger.warning(f"ESPN: no data to upload for season {season}")

    return all_uris
