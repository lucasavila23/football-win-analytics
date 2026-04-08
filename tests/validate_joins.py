# =============================================================================
# JOIN VALIDATION — Understat ↔ ESPN, 2023 season
# =============================================================================
# Diagnostic (not production code). Verifies that normalize_name() produces
# clean joins at both match level and player level across all 5 leagues.
#
# Targets:
#   Match rate    ≥ 95% per league
#   Player→match  ≥ 90% per league
#
# Any league below these thresholds is flagged and problem names are printed
# so they can be added to pipeline/utils.py before scrapers are built.
#
# Run: python tests/validate_joins.py
# =============================================================================

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import soccerdata as sd

from pipeline.config import LEAGUES
from pipeline.utils import normalize_name

SEASON = "2023"
LEAGUES_5 = {k: v for k, v in LEAGUES.items() if k != "champions_league"}

MATCH_RATE_THRESHOLD  = 95.0
PLAYER_RATE_THRESHOLD = 90.0

SEP  = "=" * 72
SEP2 = "-" * 72


def _norm_df_teams(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].apply(normalize_name)


def _extract_date(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d")


# =============================================================================
# DATA LOADING (cached from soccerdata)
# =============================================================================

def load_understat_matches(league_id: str) -> pd.DataFrame:
    df = sd.Understat(leagues=league_id, seasons=SEASON).read_team_match_stats().reset_index()
    df.columns = [c.lower() for c in df.columns]
    return df


def load_understat_players(league_id: str) -> pd.DataFrame:
    df = sd.Understat(leagues=league_id, seasons=SEASON).read_player_match_stats().reset_index()
    df.columns = [c.lower() for c in df.columns]
    return df


def load_espn_lineups(league_id: str) -> pd.DataFrame:
    df = sd.ESPN(leagues=league_id, seasons=SEASON).read_lineup().reset_index()
    df.columns = [c.lower() for c in df.columns]
    return df


# =============================================================================
# MATCH-LEVEL JOIN
# =============================================================================

def validate_match_join(league_key: str, league_id: str) -> dict:
    print(f"\n  [{league_key}] Loading Understat matches...")
    ud_matches = load_understat_matches(league_id)

    print(f"  [{league_key}] Loading ESPN lineups...")
    espn       = load_espn_lineups(league_id)

    # --- Normalise Understat match rows ---
    ud_matches["date_str"]        = _extract_date(ud_matches, "date")
    ud_matches["home_norm"]       = _norm_df_teams(ud_matches, "home_team")
    ud_matches["away_norm"]       = _norm_df_teams(ud_matches, "away_team")

    # One row per unique match from ESPN (date + home + away)
    # ESPN date field may be stored under "game" or "date"
    if "game" in espn.columns:
        espn["date_str"] = espn["game"].apply(
            lambda x: str(x).split(" ")[0] if pd.notna(x) else None
        )
    elif "date" in espn.columns:
        espn["date_str"] = _extract_date(espn, "date")
    else:
        print(f"  [{league_key}] ERROR: no date column in ESPN data")
        return {"match_rate": 0.0, "matched": 0, "ud_total": len(ud_matches)}

    # ESPN team column
    team_col = "team" if "team" in espn.columns else None
    if team_col is None:
        print(f"  [{league_key}] ERROR: no team column in ESPN data")
        return {"match_rate": 0.0, "matched": 0, "ud_total": len(ud_matches)}

    espn["team_norm"] = _norm_df_teams(espn, team_col)

    # Build unique ESPN match frame: one row per date+home+away
    # ESPN lineups are player-level; derive matches by grouping date+teams
    # We need home and away per match — use the game/fixture context
    # ESPN lineups have an "is_home" flag or we can derive from match context
    # Fall back: build all unique (date, team) pairs then self-join as home/away
    espn_dates_teams = (
        espn[["date_str", "team_norm"]]
        .drop_duplicates()
        .dropna(subset=["date_str"])
    )

    # Cross-join same date teams to find home/away pairs that appear in Understat
    # More robust: join Understat matches to ESPN via date + home_norm + away_norm
    # by looking for any ESPN team on that date matching home or away

    # Build a set of (date, norm_team) from ESPN
    espn_date_team_set = set(
        zip(espn_dates_teams["date_str"], espn_dates_teams["team_norm"])
    )

    # For each Understat match, check if BOTH home and away appear in ESPN on same date
    ud_matches["home_in_espn"] = ud_matches.apply(
        lambda r: (r["date_str"], r["home_norm"]) in espn_date_team_set, axis=1
    )
    ud_matches["away_in_espn"] = ud_matches.apply(
        lambda r: (r["date_str"], r["away_norm"]) in espn_date_team_set, axis=1
    )
    ud_matches["joined"] = ud_matches["home_in_espn"] & ud_matches["away_in_espn"]

    matched   = ud_matches["joined"].sum()
    ud_total  = len(ud_matches)
    match_rate = matched / ud_total * 100 if ud_total else 0.0

    # Unmatched rows
    unmatched = ud_matches[~ud_matches["joined"]].copy()

    icon = "✅" if match_rate >= MATCH_RATE_THRESHOLD else "❌"
    print(f"\n  {icon} [{league_key}] Match join:")
    print(f"      Understat matches : {ud_total}")
    print(f"      Joined            : {matched}")
    print(f"      Unmatched         : {len(unmatched)}")
    print(f"      Match rate        : {match_rate:.1f}%")

    if len(unmatched) > 0:
        print(f"\n      Unmatched Understat matches (raw → normalised):")
        for _, row in unmatched.head(20).iterrows():
            home_miss = "✗" if not row["home_in_espn"] else " "
            away_miss = "✗" if not row["away_in_espn"] else " "
            print(
                f"        {row['date_str']}  "
                f"[{home_miss}] {row['home_team']!r:30s} → {row['home_norm']!r:30s}  |  "
                f"[{away_miss}] {row['away_team']!r:30s} → {row['away_norm']!r}"
            )
        # Also print what ESPN teams appear on those dates (to help diagnose)
        unmatched_dates = set(unmatched["date_str"].unique())
        espn_on_those_dates = espn_dates_teams[
            espn_dates_teams["date_str"].isin(unmatched_dates)
        ]["team_norm"].unique()
        print(f"\n      ESPN normalised teams on unmatched dates:")
        for t in sorted(espn_on_those_dates):
            print(f"        {t!r}")

    return {
        "match_rate":  match_rate,
        "matched":     int(matched),
        "ud_total":    ud_total,
        "unmatched_df": unmatched,
        "ud_matches":  ud_matches,
        "espn":        espn,
    }


# =============================================================================
# PLAYER-LEVEL JOIN
# =============================================================================

def validate_player_join(league_key: str, league_id: str, match_result: dict) -> dict:
    print(f"\n  [{league_key}] Loading Understat player stats...")
    ud_players = load_understat_players(league_id)

    ud_matches = match_result.get("ud_matches")
    espn       = match_result.get("espn")

    if ud_matches is None or espn is None:
        print(f"  [{league_key}] Skipping player join — match data unavailable")
        return {"player_match_rate": 0.0, "overlap_rate": 0.0}

    # --- Player → Match linkage ---
    # Understat player_stats: date is the first 10 chars of the 'game' column
    # e.g. "2023-08-11 Almeria-Rayo Vallecano"
    date_col = "date" if "date" in ud_players.columns else "game"
    ud_players["date_str"] = ud_players[date_col].apply(
        lambda x: str(x)[:10] if pd.notna(x) else None
    )
    ud_players["team_norm"] = ud_players["team"].apply(normalize_name)

    # Build a set of valid (date, home_norm) and (date, away_norm) from JOINED matches
    joined_matches = ud_matches[ud_matches["joined"]].copy()
    valid_date_team = set(
        zip(joined_matches["date_str"], joined_matches["home_norm"])
    ) | set(
        zip(joined_matches["date_str"], joined_matches["away_norm"])
    )

    ud_players["links_to_match"] = ud_players.apply(
        lambda r: (r["date_str"], r["team_norm"]) in valid_date_team, axis=1
    )

    linked       = ud_players["links_to_match"].sum()
    total_players = len(ud_players)
    player_match_rate = linked / total_players * 100 if total_players else 0.0

    orphaned = ud_players[~ud_players["links_to_match"]]

    icon = "✅" if player_match_rate >= PLAYER_RATE_THRESHOLD else "❌"
    print(f"\n  {icon} [{league_key}] Player→match linkage:")
    print(f"      Understat players : {total_players}")
    print(f"      Linked to match   : {linked}")
    print(f"      Orphaned          : {len(orphaned)}")
    print(f"      Player→match rate : {player_match_rate:.1f}%")

    if len(orphaned) > 0:
        player_col = "player" if "player" in orphaned.columns else orphaned.columns[0]
        print(f"\n      Sample orphaned player rows (up to 20):")
        for _, row in orphaned.head(20).iterrows():
            print(f"        {row['date_str']}  team={row['team']!r:30s} → {row['team_norm']!r}  player={row.get(player_col, '?')!r}")

    # --- ESPN ↔ Understat player name overlap ---
    # For joined matches, compare ESPN lineup player names to Understat player names
    espn_player_col   = "player" if "player" in espn.columns else None
    udp_player_col    = "player" if "player" in ud_players.columns else None

    overlap_rate = None
    if espn_player_col and udp_player_col:
        # Restrict to joined matches only
        valid_dates = set(joined_matches["date_str"])
        espn_on_valid = espn[espn["date_str"].isin(valid_dates)].copy()
        udp_on_valid  = ud_players[ud_players["links_to_match"]].copy()

        espn_players = set(espn_on_valid[espn_player_col].dropna().str.lower().str.strip())
        udp_players  = set(udp_on_valid[udp_player_col].dropna().str.lower().str.strip())

        overlap  = espn_players & udp_players
        overlap_rate = len(overlap) / len(espn_players) * 100 if espn_players else 0.0

        only_espn = espn_players - udp_players
        print(f"\n  📋 [{league_key}] ESPN↔Understat player name overlap:")
        print(f"      ESPN unique players   : {len(espn_players)}")
        print(f"      Understat players     : {len(udp_players)}")
        print(f"      In both sources       : {len(overlap)}")
        print(f"      ESPN only (no Understat stats): {len(only_espn)}")
        print(f"      Overlap rate          : {overlap_rate:.1f}%")

        if only_espn:
            sample = sorted(only_espn)[:20]
            print(f"\n      Sample ESPN players not in Understat (first 20):")
            for p in sample:
                print(f"        {p!r}")

    return {
        "player_match_rate": player_match_rate,
        "overlap_rate":      overlap_rate or 0.0,
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(SEP)
    print("  JOIN VALIDATION — Understat ↔ ESPN, 2023 season")
    print("  normalize_name() applied to all team name joins")
    print(SEP)

    match_results  = {}
    player_results = {}

    # --- Per-league validation ---
    for league_key, league_id in LEAGUES_5.items():
        print(f"\n{SEP2}")
        print(f"  LEAGUE: {league_key}  ({league_id})")
        print(SEP2)

        try:
            m_result = validate_match_join(league_key, league_id)
        except Exception as e:
            import traceback
            print(f"  ❌ Match join FAILED: {e}")
            traceback.print_exc()
            m_result = {"match_rate": 0.0, "matched": 0, "ud_total": 0}

        match_results[league_key] = m_result

        try:
            p_result = validate_player_join(league_key, league_id, m_result)
        except Exception as e:
            import traceback
            print(f"  ❌ Player join FAILED: {e}")
            traceback.print_exc()
            p_result = {"player_match_rate": 0.0, "overlap_rate": 0.0}

        player_results[league_key] = p_result

    # --- Summary table ---
    print(f"\n{SEP}")
    print("  FINAL SUMMARY")
    print(SEP)
    print(
        f"  {'League':<20} {'Match rate':>12} {'Player→match':>14} {'ESPN↔UD overlap':>17}"
    )
    print(f"  {'-'*20}  {'-'*11}  {'-'*13}  {'-'*16}")

    all_pass = True
    for lk in LEAGUES_5:
        mr  = match_results.get(lk, {}).get("match_rate", 0.0)
        pmr = player_results.get(lk, {}).get("player_match_rate", 0.0)
        ovr = player_results.get(lk, {}).get("overlap_rate", 0.0)

        m_icon  = "✅" if mr  >= MATCH_RATE_THRESHOLD  else "❌"
        p_icon  = "✅" if pmr >= PLAYER_RATE_THRESHOLD else "❌"
        o_icon  = "✅" if ovr >= 50.0                  else "⚠️ "  # overlap expected lower (substitutes, goalkeepers missing from xG)

        if mr < MATCH_RATE_THRESHOLD or pmr < PLAYER_RATE_THRESHOLD:
            all_pass = False

        print(
            f"  {lk:<20} {m_icon} {mr:>7.1f}%    {p_icon} {pmr:>8.1f}%    {o_icon} {ovr:>8.1f}%"
        )

    print()
    if all_pass:
        print("  ✅ ALL LEAGUES PASS — safe to proceed to scraper builds")
    else:
        print("  ❌ SOME LEAGUES BELOW THRESHOLD — fix normalize_name() before building scrapers")

    print(SEP)
