# =============================================================================
# FOOTBALL ANALYTICS — MASTER ORCHESTRATOR
# =============================================================================
# Usage:
#   python main.py --seasons 2023 --leagues la_liga
#   python main.py --seasons 2024                         # Current season, all leagues
#   python main.py --seasons 2014 2015 --leagues la_liga  # Backfill specific
#   python main.py --backfill                             # Full historical load
#
# Execution order per (season, league) — never deviate:
#   1. Fetch Understat matches   → time it
#   2. Fetch Understat players   → time it
#   3. Upload both to GCS        → time it
#   4. Fetch ESPN lineups        → time it
#   5. Upload lineups to GCS     → time it
#   6. Load all three into BQ    → time each table
#   7. Print PipelineTimer summary
#   8. Save timing JSON → docs/pipeline_timings/
#
# Rules:
#   - overwrite=False on all GCS uploads — reruns skip existing files
#   - Never run step N+1 before step N completes successfully
#   - All status via logger.info/warning/error — never bare print()
#   - Only the timing summary table uses print()
#   - StatsBomb scraper is NOT wired here (too slow for initial validation)
# =============================================================================

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from pipeline.config import CURRENT_SEASON, HISTORICAL_SEASONS, LEAGUES
from pipeline.loaders.bigquery_loader import load_parquet_from_gcs
from pipeline.loaders.gcs_loader import upload_multiple
from pipeline.scrapers.espn_scraper import scrape_espn_league_season
from pipeline.scrapers.understat_scraper import scrape_understat_league_season
from pipeline.utils import PipelineTimer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_TIMINGS_DIR = Path(__file__).parent / "docs" / "pipeline_timings"


def _save_timing_json(timer: PipelineTimer, league: str, season: str) -> None:
    """
    Persist timing results as JSON to docs/pipeline_timings/.

    Filename: {date}_{league}_{season}.json
    Errors are logged but do not abort the pipeline.
    """
    _TIMINGS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    filename = _TIMINGS_DIR / f"{today}_{league}_{season}.json"

    payload = {
        "date":    today,
        "league":  league,
        "season":  season,
        "timings": timer.to_dict(),
    }
    try:
        filename.write_text(json.dumps(payload, indent=2))
        logger.info(f"Timing JSON saved → {filename}")
    except Exception as exc:
        logger.warning(f"Could not save timing JSON: {exc}")


def _run_league_season(league: str, season: str, timer: PipelineTimer) -> bool:
    """
    Execute the full pipeline for a single (league, season) pair.

    Returns True on success, False if any step fails (caller saves timings
    and exits). All timings are recorded onto the shared PipelineTimer.
    """
    logger.info(f"━━━ Starting pipeline: {league} / {season} ━━━")

    # ──────────────────────────────────────────────────────────────
    # Steps 1+2 — Fetch Understat matches + player_stats (one call)
    # scrape_understat_league_season() fetches both in sequence internally
    # and logs per-table timings. We time the combined fetch here.
    # ──────────────────────────────────────────────────────────────
    logger.info(f"[1/5] Understat fetch (matches + player_stats): {league}/{season}")
    timer.start(f"understat / {league} / {season} / total")
    try:
        matches_df, players_df = scrape_understat_league_season(league, season)
    except Exception as exc:
        logger.error(f"Understat fetch failed ({league}/{season}): {exc}")
        timer.stop(f"understat / {league} / {season} / total")
        return False
    timer.stop(f"understat / {league} / {season} / total")

    if matches_df is None or matches_df.empty:
        logger.error(f"Understat matches returned empty for {league}/{season}")
        return False
    players_ok = players_df is not None and not players_df.empty
    if not players_ok:
        logger.warning(f"Understat player_stats unavailable for {league}/{season} — will load matches only")

    # ──────────────────────────────────────────────────────────────
    # Step 2 — Upload Understat files to GCS
    # ──────────────────────────────────────────────────────────────
    logger.info(f"[2/5] GCS upload Understat: {league}/{season}")
    timer.start(f"gcs_upload / understat_{league}_{season}")
    gcs_items = [
        {
            "df":        matches_df,
            "league":    league,
            "source":    "understat",
            "season":    season,
            "table":     "matches",
            "overwrite": False,
        },
    ]
    if players_ok:
        gcs_items.append({
            "df":        players_df,
            "league":    league,
            "source":    "understat",
            "season":    season,
            "table":     "player_stats",
            "overwrite": False,
        })
    try:
        upload_multiple(gcs_items)
    except Exception as exc:
        logger.error(f"GCS upload (Understat) failed ({league}/{season}): {exc}")
        timer.stop(f"gcs_upload / understat_{league}_{season}")
        return False
    timer.stop(f"gcs_upload / understat_{league}_{season}")

    # ──────────────────────────────────────────────────────────────
    # Step 3 — Fetch ESPN lineups
    # ──────────────────────────────────────────────────────────────
    logger.info(f"[3/5] ESPN lineups fetch: {league}/{season}")
    timer.start(f"espn / {league} / {season} / lineups")
    espn_ok = True
    try:
        lineups_df = scrape_espn_league_season(league, season)
    except Exception as exc:
        logger.warning(f"ESPN lineups fetch failed ({league}/{season}): {exc} — skipping ESPN for this season")
        lineups_df = None
        espn_ok = False
    timer.stop(f"espn / {league} / {season} / lineups")

    if lineups_df is None or lineups_df.empty:
        if espn_ok:
            logger.warning(f"ESPN lineups returned empty for {league}/{season} — skipping ESPN steps")
        espn_ok = False

    # ──────────────────────────────────────────────────────────────
    # Step 4 — Upload ESPN lineups to GCS (skipped if ESPN unavailable)
    # ──────────────────────────────────────────────────────────────
    if espn_ok:
        logger.info(f"[4/5] GCS upload ESPN: {league}/{season}")
        timer.start(f"gcs_upload / espn_{league}_{season}")
        try:
            upload_multiple([
                {
                    "df":        lineups_df,
                    "league":    league,
                    "source":    "espn",
                    "season":    season,
                    "table":     "lineups",
                    "overwrite": False,
                },
            ])
        except Exception as exc:
            logger.error(f"GCS upload (ESPN) failed ({league}/{season}): {exc}")
            timer.stop(f"gcs_upload / espn_{league}_{season}")
            return False
        timer.stop(f"gcs_upload / espn_{league}_{season}")
    else:
        logger.info(f"[4/5] GCS upload ESPN: skipped (no data for {league}/{season})")

    # ──────────────────────────────────────────────────────────────
    # Step 5 — Load GCS → BigQuery raw
    # ──────────────────────────────────────────────────────────────
    logger.info(f"[5/5] BigQuery load: {league}/{season}")

    bq_steps = [
        ("understat", "matches", f"bq_load / {league} / {season} / understat_matches"),
    ]
    if players_ok:
        bq_steps.append(("understat", "player_stats", f"bq_load / {league} / {season} / understat_player_stats"))
    if espn_ok:
        bq_steps.append(("espn", "lineups", f"bq_load / {league} / {season} / espn_lineups"))

    for source, table, label in bq_steps:
        timer.start(label)
        try:
            load_parquet_from_gcs(
                league=league,
                source=source,
                season=season,
                table=table,
                mode="WRITE_APPEND",
            )
        except Exception as exc:
            logger.error(
                f"BigQuery load failed ({source}/{table} for {league}/{season}): {exc}"
            )
            timer.stop(label)
            return False
        timer.stop(label)

    logger.info(f"━━━ Completed: {league} / {season} ━━━")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Football Analytics Pipeline Orchestrator"
    )
    parser.add_argument(
        "--seasons", nargs="+",
        help="Seasons to ingest (e.g. 2022 2023 2024)",
    )
    parser.add_argument(
        "--leagues", nargs="+", choices=list(LEAGUES.keys()),
        default=list(LEAGUES.keys()),
        help="Leagues to ingest (default: all)",
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Run full historical backfill (2014 → 2023)",
    )
    args = parser.parse_args()

    seasons = HISTORICAL_SEASONS if args.backfill else (args.seasons or [CURRENT_SEASON])
    leagues = args.leagues

    logger.info("FOOTBALL ANALYTICS PIPELINE")
    logger.info("============================")
    logger.info(f"Seasons : {seasons}")
    logger.info(f"Leagues : {leagues}")

    timer = PipelineTimer()
    timer.start("pipeline_total")

    for season in seasons:
        for league in leagues:
            success = _run_league_season(league, season, timer)

            if not success:
                logger.error(
                    f"Pipeline FAILED for {league}/{season} — "
                    "saving partial timings and exiting"
                )
                timer.stop("pipeline_total")
                timer.summary()
                _save_timing_json(timer, league, season)
                sys.exit(1)

            _save_timing_json(timer, league, season)

    timer.stop("pipeline_total")
    timer.summary()


if __name__ == "__main__":
    main()
