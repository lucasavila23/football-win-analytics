# =============================================================================
# STATSBOMB COVERAGE VALIDATION
# =============================================================================
# Validates StatsBomb Open Data availability for our target leagues and seasons.
# Read-only — no GCS or BigQuery writes.
#
# Run: python tests/validate_statsbomb.py
# =============================================================================

import logging
import sys
from collections import defaultdict

import pandas as pd
from statsbombpy import sb

from pipeline.config import ALL_SEASONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# StatsBomb competition names that map to our league keys
TARGET_COMPETITIONS = {
    "La Liga":           "la_liga",
    "Premier League":    "premier_league",
    "1. Bundesliga":     "bundesliga",
    "Serie A":           "serie_a",
    "Ligue 1":           "ligue_1",
    "Champions League":  "champions_league",
}

PRESSING_COLUMNS = [
    "type",
    "press",
    "under_pressure",
    "counterpress",
    "pass_length",
    "pass_progressive_distance",
    "carry_progressive_distance",
]

SEP = "=" * 80


def _parse_season_start_year(season_name: str) -> str:
    """Extract the start year from a StatsBomb season name like '2019/2020' or '2019'."""
    return season_name.split("/")[0].strip()


# =============================================================================
# SECTION 1 — Competition inventory
# =============================================================================

def section1_competition_inventory():
    print(f"\n{SEP}")
    print("  SECTION 1 — Competition Inventory")
    print(SEP)

    logger.info("Fetching all StatsBomb competitions...")
    comps = sb.competitions()

    # Filter to our target competitions
    matched = comps[comps["competition_name"].isin(TARGET_COMPETITIONS.keys())].copy()

    if matched.empty:
        logger.error("No matching competitions found! Check TARGET_COMPETITIONS names.")
        sys.exit(1)

    logger.info(f"Found {len(matched)} competition-seasons across our target leagues")

    # Pull match count for each competition-season
    rows = []
    for _, row in matched.iterrows():
        try:
            matches_df = sb.matches(
                competition_id=int(row["competition_id"]),
                season_id=int(row["season_id"])
            )
            match_count = len(matches_df)
        except Exception as e:
            logger.warning(f"Could not fetch matches for {row['competition_name']} {row['season_name']}: {e}")
            match_count = -1

        rows.append({
            "competition_name": row["competition_name"],
            "competition_id":   int(row["competition_id"]),
            "season_id":        int(row["season_id"]),
            "season_name":      row["season_name"],
            "match_count":      match_count,
        })

    inventory = pd.DataFrame(rows).sort_values(["competition_name", "season_name"])

    print(f"\n{'Competition':<25} {'comp_id':>8} {'season_id':>10} {'Season':<15} {'Matches':>8}")
    print("-" * 72)
    for _, r in inventory.iterrows():
        print(
            f"{r['competition_name']:<25} {r['competition_id']:>8} "
            f"{r['season_id']:>10} {r['season_name']:<15} {r['match_count']:>8}"
        )

    return inventory


# =============================================================================
# SECTION 2 — Column/null audit for one sample season per league
# =============================================================================

def section2_column_audit(inventory: pd.DataFrame):
    print(f"\n{SEP}")
    print("  SECTION 2 — Column & Null Audit (most recent season per league)")
    print(SEP)

    # Pick the most recent season for each competition (highest season_id heuristic: max season_id)
    # Use season_name start year for ordering
    inventory = inventory.copy()
    inventory["start_year"] = inventory["season_name"].apply(_parse_season_start_year)
    latest_per_comp = (
        inventory.sort_values("start_year", ascending=False)
        .groupby("competition_name")
        .first()
        .reset_index()
    )

    sample_events_by_league = {}

    for _, row in latest_per_comp.iterrows():
        comp_name = row["competition_name"]
        league_key = TARGET_COMPETITIONS[comp_name]
        season_name = row["season_name"]

        print(f"\n--- {comp_name} | {season_name} ---")
        logger.info(f"Fetching events: competition_id={int(row['competition_id'])}, season_id={int(row['season_id'])}")

        try:
            # Pull a small sample by fetching events for the first match only
            matches_df = sb.matches(
                competition_id=int(row["competition_id"]),
                season_id=int(row["season_id"])
            )
            if matches_df.empty:
                print("  No matches found for this season — skipping")
                continue

            first_match_id = int(matches_df["match_id"].iloc[0])
            events = sb.events(match_id=first_match_id)
            print(f"  Sample from match_id={first_match_id}: {len(events)} events, {len(events.columns)} columns")

        except Exception as e:
            logger.warning(f"  Could not fetch events: {e}")
            continue

        # Column list
        cols = sorted(events.columns.tolist())
        print(f"\n  All columns ({len(cols)}):")
        for i in range(0, len(cols), 5):
            print("    " + ", ".join(cols[i:i+5]))

        # Pressing column presence
        print(f"\n  Pressing-relevant columns:")
        for col in PRESSING_COLUMNS:
            if col in events.columns:
                null_pct = events[col].isna().mean() * 100
                print(f"    ✓ {col:<40} null={null_pct:.1f}%")
            else:
                print(f"    ✗ {col:<40} NOT PRESENT")

        # 5-row sample (select a few readable columns)
        sample_cols = [c for c in ["type", "team", "player", "minute", "second", "under_pressure"] if c in events.columns]
        if sample_cols:
            print(f"\n  5-row sample ({', '.join(sample_cols)}):")
            print(events[sample_cols].head(5).to_string(index=False))

        sample_events_by_league[league_key] = {
            "events": events,
            "season_name": season_name,
            "competition_id": int(row["competition_id"]),
            "season_id": int(row["season_id"]),
        }

    return sample_events_by_league


# =============================================================================
# SECTION 3 — Join viability check
# =============================================================================

def section3_join_viability(inventory: pd.DataFrame, sample_events_by_league: dict):
    print(f"\n{SEP}")
    print("  SECTION 3 — Join Viability: StatsBomb team names vs Understat format")
    print(SEP)

    # Use La Liga if available, else first available league
    check_league = None
    for league_key in ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1"]:
        if league_key in sample_events_by_league:
            check_league = league_key
            break

    if check_league is None:
        print("  No sample data available for join check")
        return

    sample = sample_events_by_league[check_league]
    comp_id = sample["competition_id"]
    season_id = sample["season_id"]
    season_name = sample["season_name"]
    comp_name = [k for k, v in TARGET_COMPETITIONS.items() if v == check_league][0]

    print(f"\n  Checking: {comp_name} | {season_name}")

    try:
        matches_df = sb.matches(competition_id=comp_id, season_id=season_id)
    except Exception as e:
        logger.warning(f"  Could not fetch matches: {e}")
        return

    print(f"\n  matches_df columns: {list(matches_df.columns)}")
    print(f"\n  match_date dtype: {matches_df['match_date'].dtype if 'match_date' in matches_df.columns else 'NOT PRESENT'}")

    # Show team name format from StatsBomb
    if "home_team" in matches_df.columns:
        sb_home_teams = matches_df["home_team"].unique()[:10]
        print(f"\n  StatsBomb home_team values (first 10):")
        for t in sb_home_teams:
            print(f"    '{t}'")
    else:
        print("  'home_team' column not present in matches_df")

    print(f"\n  Example Understat team names (from config context):")
    understat_examples = [
        "Real Madrid", "FC Barcelona", "Atletico Madrid",
        "Bayern Munich", "Borussia Dortmund", "Manchester City",
    ]
    for t in understat_examples:
        print(f"    '{t}'")

    print(f"\n  → Name format differences will require normalize_name() from pipeline/utils.py")
    print(f"  → Join key: match_date + normalized home_team + normalized away_team")

    # Show 5 full match rows
    display_cols = [c for c in ["match_id", "match_date", "home_team", "away_team", "home_score", "away_score"] if c in matches_df.columns]
    print(f"\n  5 sample matches:")
    print(matches_df[display_cols].head(5).to_string(index=False))


# =============================================================================
# SECTION 4 — Coverage summary table
# =============================================================================

def section4_coverage_summary(inventory: pd.DataFrame):
    print(f"\n{SEP}")
    print("  SECTION 4 — Coverage Summary")
    print(SEP)

    # Our Understat seasons (start years only)
    our_seasons = set(ALL_SEASONS)  # e.g. {"2014", "2015", ..., "2024"}

    print(f"\n  Our Understat seasons ({len(our_seasons)}): {sorted(our_seasons)}")

    print(f"\n  {'League':<20} {'SB seasons':>12} {'Our seasons':>12} {'Overlap':>10}")
    print(f"  {'-'*60}")

    for comp_name, league_key in TARGET_COMPETITIONS.items():
        comp_rows = inventory[inventory["competition_name"] == comp_name]
        if comp_rows.empty:
            print(f"  {comp_name:<20} {'0':>12} {len(our_seasons):>12} {'0':>10}")
            continue

        sb_start_years = set(comp_rows["season_name"].apply(_parse_season_start_year))
        overlap = sb_start_years & our_seasons
        print(
            f"  {comp_name:<20} {len(sb_start_years):>12} {len(our_seasons):>12} {len(overlap):>10}"
        )
        if overlap:
            print(f"    Overlapping seasons: {sorted(overlap)}")
        if sb_start_years - our_seasons:
            print(f"    StatsBomb only: {sorted(sb_start_years - our_seasons)}")

    print(f"\n  NOTE: StatsBomb seasons outside our Understat range will not be loaded.")
    print(f"  NOTE: Only overlapping seasons will be added to STATSBOMB_SEASON_MAP in config.py.")

    # Also print a machine-readable config snippet for STATSBOMB_SEASON_MAP
    print(f"\n{SEP}")
    print("  CONFIG SNIPPET — STATSBOMB_SEASON_MAP (copy into pipeline/config.py after Task 1)")
    print(SEP)
    print("\nSTATSBOMB_SEASON_MAP = {")

    inventory_copy = inventory.copy()
    inventory_copy["start_year"] = inventory_copy["season_name"].apply(_parse_season_start_year)

    for comp_name, league_key in TARGET_COMPETITIONS.items():
        comp_rows = inventory_copy[inventory_copy["competition_name"] == comp_name]
        for _, row in comp_rows.sort_values("start_year").iterrows():
            start_year = row["start_year"]
            if start_year in our_seasons:
                print(
                    f'    ("{league_key}", "{start_year}"): '
                    f'{{"competition_id": {int(row["competition_id"])}, '
                    f'"season_id": {int(row["season_id"])}, '
                    f'"season_name": "{row["season_name"]}"}}, '
                )

    print("}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(SEP)
    print("  STATSBOMB OPEN DATA — COVERAGE VALIDATION")
    print(SEP)

    inventory = section1_competition_inventory()
    sample_events = section2_column_audit(inventory)
    section3_join_viability(inventory, sample_events)
    section4_coverage_summary(inventory)

    print(f"\n{SEP}")
    print("  VALIDATION COMPLETE")
    print(SEP)
