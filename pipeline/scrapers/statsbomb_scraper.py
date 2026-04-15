# =============================================================================
# STATSBOMB SCRAPER
# =============================================================================
# Fetches event-level data from StatsBomb Open Data (statsbombpy).
# No authentication required for open data.
#
# Two public functions:
#   scrape_events(league, season)        → raw events DataFrame (one row/event)
#   scrape_match_summary(league, season) → aggregated per-match metrics
#
# Coverage is limited to seasons in STATSBOMB_SEASON_MAP in pipeline/config.py.
# Champions League is excluded — open data has only 1 match/season there.
#
# Pressing counts use type == "Pressure" (the `press` column does not exist
# in StatsBomb open data). Progressive carries are computed from coordinates
# since `carry_progressive_distance` is also absent from open data.
#
# GCS blob paths:
#   bronze/{league}/statsbomb/{season}/events.parquet
#   bronze/{league}/statsbomb/{season}/match_summary.parquet
# =============================================================================

import logging
import math
import time

import pandas as pd
from dotenv import load_dotenv
from statsbombpy import sb

from pipeline.config import STATSBOMB_COMPETITION_META, STATSBOMB_SEASON_MAP
from pipeline.utils import normalize_name

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# StatsBomb pitch: 120 yards long × 80 yards wide.
# A carry is "progressive" if it moves the ball forward (toward goal, x=120)
# and covers at least 9.11 metres (~10 yards) — StatsBomb's own threshold.
_PROGRESSIVE_CARRY_MIN_DISTANCE = 9.11  # metres (StatsBomb pitch units)


def _is_coverage_available(league: str, season: str) -> bool:
    """Return True if (league, season) exists in STATSBOMB_SEASON_MAP."""
    return (league, season) in STATSBOMB_SEASON_MAP


def _compute_progressive_carries(events: pd.DataFrame) -> pd.DataFrame:
    """
    Add a boolean `is_progressive_carry` column to events.

    A carry is progressive if:
      1. event type is "Carry"
      2. carry_end_x > carry_start_x  (ball moves toward opponent goal)
      3. euclidean distance >= _PROGRESSIVE_CARRY_MIN_DISTANCE

    StatsBomb `location` column = [x, y].
    StatsBomb `carry_end_location` column = [end_x, end_y].
    Both are list-type and may be NaN on non-carry rows.
    """
    carry_mask = events["type"] == "Carry"
    events = events.copy()
    events["is_progressive_carry"] = False

    if not carry_mask.any():
        return events

    carry_rows = events[carry_mask].copy()

    # Extract coordinates — location and carry_end_location are list columns
    carry_rows["start_x"] = carry_rows["location"].apply(
        lambda loc: loc[0] if isinstance(loc, list) else float("nan")
    )
    carry_rows["end_x"] = carry_rows["carry_end_location"].apply(
        lambda loc: loc[0] if isinstance(loc, list) else float("nan")
    )
    carry_rows["start_y"] = carry_rows["location"].apply(
        lambda loc: loc[1] if isinstance(loc, list) else float("nan")
    )
    carry_rows["end_y"] = carry_rows["carry_end_location"].apply(
        lambda loc: loc[1] if isinstance(loc, list) else float("nan")
    )

    dx = carry_rows["end_x"] - carry_rows["start_x"]
    dy = carry_rows["end_y"] - carry_rows["start_y"]
    distance = (dx ** 2 + dy ** 2).apply(math.sqrt)

    progressive = (carry_rows["end_x"] > carry_rows["start_x"]) & (distance >= _PROGRESSIVE_CARRY_MIN_DISTANCE)
    events.loc[carry_mask, "is_progressive_carry"] = progressive.values

    return events


def scrape_events(league: str, season: str) -> pd.DataFrame | None:
    """
    Fetch all StatsBomb events for a league + season.

    Args:
        league:  League key from config (e.g. 'la_liga')
        season:  Season start year as string (e.g. '2015')

    Returns:
        DataFrame of all events (one row per event), with `league` and `season`
        columns added. Returns None if the league/season is not in coverage.
    """
    if not _is_coverage_available(league, season):
        logger.warning(
            f"No StatsBomb coverage for {league}/{season} — skipping. "
            f"Check STATSBOMB_SEASON_MAP in pipeline/config.py."
        )
        return None

    mapping = STATSBOMB_SEASON_MAP[(league, season)]
    meta = STATSBOMB_COMPETITION_META[league]
    season_name = mapping["season_name"]

    logger.info(
        f"Fetching events: {meta['division']} {season_name} "
        f"(competition_id={mapping['competition_id']}, season_id={mapping['season_id']})"
    )
    t0 = time.time()

    events = sb.competition_events(
        country=meta["country"],
        division=meta["division"],
        season=season_name,
        gender="male",
    )

    elapsed = time.time() - t0
    logger.info(
        f"Fetched {len(events)} events for {meta['division']} {season_name} "
        f"in {elapsed:.1f}s"
    )

    events = events.copy()
    events["league"] = league
    events["season"] = season

    return events


def scrape_match_summary(league: str, season: str) -> pd.DataFrame | None:
    """
    Aggregate StatsBomb events to one row per match with pressing/carrying metrics.

    Columns returned:
        match_date, home_team, away_team, league, season,
        home_pressures, away_pressures,
        home_under_pressure_passes, away_under_pressure_passes,
        home_progressive_carries, away_progressive_carries

    home_team and away_team are normalized via normalize_name() so they can be
    joined against Understat data without further cleaning.

    Args:
        league:  League key from config (e.g. 'la_liga')
        season:  Season start year as string (e.g. '2015')

    Returns:
        DataFrame with one row per match. Returns None if not in coverage.
    """
    if not _is_coverage_available(league, season):
        logger.warning(
            f"No StatsBomb coverage for {league}/{season} — skipping. "
            f"Check STATSBOMB_SEASON_MAP in pipeline/config.py."
        )
        return None

    mapping = STATSBOMB_SEASON_MAP[(league, season)]

    # Pull match-level data to get home/away team assignment
    logger.info(
        f"Fetching match list: competition_id={mapping['competition_id']}, "
        f"season_id={mapping['season_id']}"
    )
    matches_df = sb.matches(
        competition_id=mapping["competition_id"],
        season_id=mapping["season_id"],
    )

    # Pull raw events
    events = scrape_events(league, season)
    if events is None:
        return None

    # Mark progressive carries
    events = _compute_progressive_carries(events)

    # --- Aggregate per match_id + team ---

    # Pressures: type == "Pressure"
    pressures = (
        events[events["type"] == "Pressure"]
        .groupby(["match_id", "team"])
        .size()
        .reset_index(name="pressures")
    )

    # Under-pressure passes: type == "Pass" AND under_pressure == True
    under_pressure_passes = (
        events[(events["type"] == "Pass") & (events["under_pressure"] == True)]
        .groupby(["match_id", "team"])
        .size()
        .reset_index(name="under_pressure_passes")
    )

    # Progressive carries
    prog_carries = (
        events[events["is_progressive_carry"] == True]
        .groupby(["match_id", "team"])
        .size()
        .reset_index(name="progressive_carries")
    )

    # Merge aggregations into a single per (match_id, team) table
    team_stats = pressures.merge(under_pressure_passes, on=["match_id", "team"], how="outer")
    team_stats = team_stats.merge(prog_carries, on=["match_id", "team"], how="outer")
    team_stats = team_stats.fillna(0)
    for col in ["pressures", "under_pressure_passes", "progressive_carries"]:
        team_stats[col] = team_stats[col].astype(int)

    # Join to matches to assign home/away
    match_info = matches_df[["match_id", "match_date", "home_team", "away_team"]].copy()
    team_stats = team_stats.merge(match_info, on="match_id", how="left")

    # Pivot: one row per match with home_ and away_ prefixed columns
    rows = []
    for match_id, grp in team_stats.groupby("match_id"):
        match_row = match_info[match_info["match_id"] == match_id].iloc[0]
        home_name = match_row["home_team"]
        away_name = match_row["away_team"]

        home_stats = grp[grp["team"] == home_name]
        away_stats = grp[grp["team"] == away_name]

        def _get(df, col):
            return int(df[col].iloc[0]) if len(df) > 0 and col in df.columns else 0

        rows.append({
            "match_id":                    match_id,
            "match_date":                  match_row["match_date"],
            "home_team":                   home_name,
            "away_team":                   away_name,
            "home_pressures":              _get(home_stats, "pressures"),
            "away_pressures":              _get(away_stats, "pressures"),
            "home_under_pressure_passes":  _get(home_stats, "under_pressure_passes"),
            "away_under_pressure_passes":  _get(away_stats, "under_pressure_passes"),
            "home_progressive_carries":    _get(home_stats, "progressive_carries"),
            "away_progressive_carries":    _get(away_stats, "progressive_carries"),
            "league":                      league,
            "season":                      season,
        })

    summary = pd.DataFrame(rows)

    # Apply normalize_name so this DataFrame is join-ready against Understat
    summary["home_team"] = summary["home_team"].apply(normalize_name)
    summary["away_team"] = summary["away_team"].apply(normalize_name)
    logger.info("Applied normalize_name() to home_team and away_team")

    logger.info(
        f"Built match_summary: {len(summary)} matches for {league}/{season}"
    )
    return summary
