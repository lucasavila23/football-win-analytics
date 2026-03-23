# =============================================================================
# FOOTBALL ANALYTICS — MASTER ORCHESTRATOR
# =============================================================================
# Usage:
#   python main.py --seasons 2024                      # Current season, all leagues
#   python main.py --seasons 2014 2015 --leagues la_liga  # Backfill specific
#   python main.py --backfill                          # Full historical load
# =============================================================================

import argparse
from pipeline.config import LEAGUES, HISTORICAL_SEASONS, CURRENT_SEASON

def main():
    parser = argparse.ArgumentParser(description="Football Analytics Pipeline Orchestrator")

    parser.add_argument(
        "--seasons", nargs="+",
        help="Seasons to ingest (e.g. 2022 2023 2024)"
    )
    parser.add_argument(
        "--leagues", nargs="+", choices=list(LEAGUES.keys()),
        default=list(LEAGUES.keys()),
        help="Leagues to ingest (default: all)"
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Run full historical backfill (2014 → 2023)"
    )

    args = parser.parse_args()

    seasons = HISTORICAL_SEASONS if args.backfill else (args.seasons or [CURRENT_SEASON])
    leagues  = args.leagues

    print("\nFOOTBALL ANALYTICS PIPELINE")
    print("============================")
    print(f"Seasons : {seasons}")
    print(f"Leagues : {leagues}")
    print()

    # Scrapers will be wired in here once GCP is set up
    print("[INFO] Pipeline stubs ready — GCP setup required before ingestion.")

if __name__ == "__main__":
    main()