# =============================================================================
# SOCCERDATA FULL SOURCE VALIDATION — PARALLEL
# =============================================================================
# Strategy:
#   - Each league is fetched in its own thread simultaneously
#   - Sources run sequentially to respect rate limits
#   - Per-operation timeouts prevent silent hangs
#   - Full timing report at the end
# =============================================================================

import warnings
warnings.filterwarnings("ignore")

import os
import time
import shutil
import signal
import traceback
import pandas as pd
import soccerdata as sd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from pipeline.config import LEAGUES

# =============================================================================
# CONFIGURATION
# =============================================================================

SEASON = "2023"

UNDERSTAT_LEAGUES = {
    k: v for k, v in LEAGUES.items()
    if k != "champions_league"
}

# Timeouts per source (seconds)
# Understat player stats: ~100s per league
# ESPN: ~600s per league (380 individual requests)
# FBref: ~120s per league
# Club Elo: ~30s per team
TIMEOUTS = {
    "understat_matches": 30,
    "understat_players": 180,
    "espn":              700,
    "fbref_passing":     180,
    "fbref_misc":        180,
    "club_elo":          60,
}

# Max parallel workers
# 5 = one thread per league, all running simultaneously
MAX_WORKERS = 5

REQUIRED_UNDERSTAT_MATCH_COLS  = ["home_team", "away_team", "home_xg", "away_xg"]
REQUIRED_UNDERSTAT_PLAYER_COLS = ["player", "team", "xg", "xa", "xg_chain", "xg_buildup", "minutes"]
REQUIRED_ESPN_COLS             = ["player", "team", "position", "fouls_committed", "fouls_suffered", "saves"]
REQUIRED_FBREF_COLS            = ["team", "poss"]
REQUIRED_ELO_COLS              = ["team", "elo"]

SOCCERDATA_CACHE = os.path.expanduser("~/soccerdata")

# =============================================================================
# TIMING TRACKER
# =============================================================================

class Timer:
    def __init__(self):
        self.session_start = time.time()
        self.operations    = []

    def record(self, label, elapsed, status):
        self.operations.append({
            "label":   label,
            "elapsed": elapsed,
            "status":  status
        })

    def total(self):
        return time.time() - self.session_start

    def print_report(self):
        section("TIMING REPORT")
        print(f"  {'Operation':<55} {'Time':>8}  Status")
        print(f"  {'-'*55}  {'-'*8}  {'-'*8}")
        for op in sorted(self.operations, key=lambda x: x["elapsed"], reverse=True):
            icon = "✅" if op["status"] == "OK"      else \
                   "⏰" if op["status"] == "TIMEOUT"  else \
                   "❌" if op["status"] == "FAIL"     else "⚠️ "
            print(f"  {op['label']:<55} {op['elapsed']:>7.1f}s  {icon} {op['status']}")
        print(f"\n  {'TOTAL SESSION TIME':<55} {self.total():>7.1f}s")

TIMER = Timer()

# =============================================================================
# HELPERS
# =============================================================================

def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

def subsection(title):
    print(f"\n  ── {title}", flush=True)

def check_columns(df, required_cols, label):
    actual  = [c.lower() for c in df.columns]
    missing = [c for c in required_cols if c.lower() not in actual]
    if missing:
        print(f"    ❌ MISSING COLUMNS in {label}: {missing}")
        return False
    print(f"    ✅ All required columns present in {label}")
    return True

def check_nulls(df, cols, label):
    for col in cols:
        col_match = next((c for c in df.columns if c.lower() == col.lower()), None)
        if col_match:
            null_pct = df[col_match].isna().mean() * 100
            status   = "✅" if null_pct < 5 else "⚠️ "
            print(f"    {status} {col}: {null_pct:.1f}% nulls")

def check_volume(df, label, min_rows=100):
    n      = len(df)
    status = "✅" if n >= min_rows else "⚠️ "
    print(f"    {status} {label}: {n} rows")
    return n >= min_rows

def print_sample(df, cols, n=3):
    available = [c for c in cols if c in df.columns]
    if available:
        print(df[available].head(n).to_string(index=False))

def print_dataframe_info(df, label):
    print(f"\n    [{label}] shape: {df.shape}")
    print(f"    [{label}] dtypes:")
    for col, dtype in df.dtypes.items():
        null_count = df[col].isna().sum()
        print(f"          {col:<35} {str(dtype):<15} nulls: {null_count}")

# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

def clear_cache():
    section("CACHE MANAGEMENT")
    if os.path.exists(SOCCERDATA_CACHE):
        size_mb = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, files in os.walk(SOCCERDATA_CACHE)
            for f in files
        ) / (1024 * 1024)
        print(f"  Found cache at {SOCCERDATA_CACHE} ({size_mb:.1f} MB)")
        shutil.rmtree(SOCCERDATA_CACHE)
        print(f"  ✅ Cache cleared — all requests will be fresh network calls")
    else:
        print(f"  ℹ️  No cache found — already fresh")

# =============================================================================
# PARALLEL FETCH ENGINE
# =============================================================================

def fetch_one(task):
    """
    Execute a single fetch task and return structured result.

    Each task is a dict with:
        key:      unique identifier e.g. 'understat_matches_la_liga'
        label:    human readable label for logging
        fn:       callable that returns a DataFrame
        timeout:  seconds before giving up
    """
    key     = task["key"]
    label   = task["label"]
    fn      = task["fn"]
    timeout = task["timeout"]

    start = time.time()
    print(f"  🚀 [{label}] starting...", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=1) as inner:
            future  = inner.submit(fn)
            result  = future.result(timeout=timeout)
            elapsed = time.time() - start
            print(f"  ✅ [{label}] done in {elapsed:.1f}s", flush=True)
            return {
                "key":     key,
                "label":   label,
                "df":      result,
                "elapsed": elapsed,
                "status":  "OK",
                "error":   None
            }
    except FuturesTimeout:
        elapsed = time.time() - start
        print(f"  ⏰ [{label}] TIMEOUT after {elapsed:.0f}s", flush=True)
        return {
            "key":     key,
            "label":   label,
            "df":      None,
            "elapsed": elapsed,
            "status":  "TIMEOUT",
            "error":   f"Timed out after {timeout}s"
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ [{label}] FAILED after {elapsed:.1f}s — {e}", flush=True)
        return {
            "key":     key,
            "label":   label,
            "df":      None,
            "elapsed": elapsed,
            "status":  "FAIL",
            "error":   str(e)
        }


def run_parallel(tasks, source_label):
    """
    Run a list of tasks in parallel using a thread pool.
    Returns dict of key → result.
    """
    section(f"{source_label} — PARALLEL FETCH ({len(tasks)} leagues simultaneously)")
    start    = time.time()
    results  = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_one, task): task for task in tasks}

        for future in as_completed(futures):
            result              = future.result()
            results[result["key"]] = result
            TIMER.record(result["label"], result["elapsed"], result["status"])

    elapsed = time.time() - start
    passed  = sum(1 for r in results.values() if r["status"] == "OK")
    print(f"\n  Parallel fetch complete — {passed}/{len(tasks)} succeeded in {elapsed:.1f}s total")

    return results

# =============================================================================
# TEST 1 — UNDERSTAT (parallel across leagues)
# =============================================================================

def test_understat():
    # --- Match stats (all 5 leagues in parallel) ---
    match_tasks = [
        {
            "key":     f"matches_{lk}",
            "label":   f"Understat/matches/{lk}",
            "timeout": TIMEOUTS["understat_matches"],
            "fn":      (lambda lid: lambda: sd.Understat(
                            leagues=lid, seasons=SEASON
                        ).read_team_match_stats().reset_index())(lid),
        }
        for lk, lid in UNDERSTAT_LEAGUES.items()
    ]

    match_raw = run_parallel(match_tasks, "TEST 1a — UNDERSTAT MATCHES")

    # --- Player stats (all 5 leagues in parallel) ---
    player_tasks = [
        {
            "key":     f"players_{lk}",
            "label":   f"Understat/players/{lk}",
            "timeout": TIMEOUTS["understat_players"],
            "fn":      (lambda lid: lambda: sd.Understat(
                            leagues=lid, seasons=SEASON
                        ).read_player_match_stats().reset_index())(lid),
        }
        for lk, lid in UNDERSTAT_LEAGUES.items()
    ]

    player_raw = run_parallel(player_tasks, "TEST 1b — UNDERSTAT PLAYERS")

    # --- Analyse results ---
    section("TEST 1 — UNDERSTAT ANALYSIS")
    results = {}

    for lk in UNDERSTAT_LEAGUES:
        subsection(lk)

        m_result = match_raw.get(f"matches_{lk}", {})
        p_result = player_raw.get(f"players_{lk}", {})

        # Matches
        if m_result.get("status") != "OK":
            print(f"    ❌ Match fetch failed: {m_result.get('error')}")
            results[lk] = {"status": "FAIL"}
            continue

        matches = m_result["df"].copy()
        matches.columns = [c.lower() for c in matches.columns]
        m_cols = check_columns(matches, REQUIRED_UNDERSTAT_MATCH_COLS, "matches")
        m_vol  = check_volume(matches, "match rows", min_rows=100)
        check_nulls(matches, REQUIRED_UNDERSTAT_MATCH_COLS, "matches")
        print_dataframe_info(matches, "matches")

        # Players
        if p_result.get("status") != "OK":
            print(f"    ❌ Player fetch failed: {p_result.get('error')}")
            results[lk] = {"status": "WARN", "matches_df": matches}
            continue

        players = p_result["df"].copy()
        players.columns = [c.lower() for c in players.columns]
        p_cols = check_columns(players, REQUIRED_UNDERSTAT_PLAYER_COLS, "player_stats")
        p_vol  = check_volume(players, "player rows", min_rows=3000)
        check_nulls(players, REQUIRED_UNDERSTAT_PLAYER_COLS, "player_stats")
        print_dataframe_info(players, "player_stats")

        print(f"\n    Sample:")
        print_sample(players, ["player", "team", "xg", "xa", "xg_chain", "xg_buildup"])

        results[lk] = {
            "status":      "PASS" if all([m_cols, m_vol, p_cols, p_vol]) else "WARN",
            "match_rows":  len(matches),
            "player_rows": len(players),
            "matches_df":  matches,
            "players_df":  players
        }

    return results

# =============================================================================
# TEST 2 — ESPN (parallel across leagues)
# =============================================================================

def test_espn():
    tasks = [
        {
            "key":     f"espn_{lk}",
            "label":   f"ESPN/lineups/{lk}",
            "timeout": TIMEOUTS["espn"],
            "fn":      (lambda lid: lambda: sd.ESPN(
                            leagues=lid, seasons=SEASON
                        ).read_lineup().reset_index())(lid),
        }
        for lk, lid in UNDERSTAT_LEAGUES.items()
    ]

    raw = run_parallel(tasks, "TEST 2 — ESPN LINEUPS")

    section("TEST 2 — ESPN ANALYSIS")
    results = {}

    for lk in UNDERSTAT_LEAGUES:
        subsection(lk)
        r = raw.get(f"espn_{lk}", {})

        if r.get("status") != "OK":
            print(f"    ❌ Failed: {r.get('error')}")
            results[lk] = {"status": "FAIL"}
            continue

        lineups = r["df"].copy()
        lineups.columns = [c.lower() for c in lineups.columns]
        cols_ok = check_columns(lineups, REQUIRED_ESPN_COLS, "lineups")
        vol_ok  = check_volume(lineups, "lineup rows", min_rows=5000)
        check_nulls(lineups, REQUIRED_ESPN_COLS, "lineups")
        print_dataframe_info(lineups, "lineups")

        if "position" in lineups.columns:
            starters = (lineups["position"] != "Substitute").sum()
            subs     = (lineups["position"] == "Substitute").sum()
            print(f"\n    ✅ Starters: {starters} | Substitutes: {subs}")

        print(f"\n    Sample:")
        print_sample(lineups, ["player", "team", "position", "fouls_committed", "saves"])

        results[lk] = {
            "status":     "PASS" if all([cols_ok, vol_ok]) else "WARN",
            "rows":       len(lineups),
            "lineups_df": lineups
        }

    return results

# =============================================================================
# TEST 3 — FBREF (parallel across leagues)
# =============================================================================

def test_fbref():
    passing_tasks = [
        {
            "key":     f"fbref_passing_{lk}",
            "label":   f"FBref/passing/{lk}",
            "timeout": TIMEOUTS["fbref_passing"],
            "fn":      (lambda lid: lambda: sd.FBref(
                            leagues=lid, seasons=SEASON
                        ).read_team_match_stats(stat_type="passing").reset_index())(lid),
        }
        for lk, lid in UNDERSTAT_LEAGUES.items()
    ]

    misc_tasks = [
        {
            "key":     f"fbref_misc_{lk}",
            "label":   f"FBref/misc/{lk}",
            "timeout": TIMEOUTS["fbref_misc"],
            "fn":      (lambda lid: lambda: sd.FBref(
                            leagues=lid, seasons=SEASON
                        ).read_team_match_stats(stat_type="misc").reset_index())(lid),
        }
        for lk, lid in UNDERSTAT_LEAGUES.items()
    ]

    passing_raw = run_parallel(passing_tasks, "TEST 3a — FBREF PASSING")
    misc_raw    = run_parallel(misc_tasks,    "TEST 3b — FBREF MISC")

    section("TEST 3 — FBREF ANALYSIS")
    results = {}

    for lk in UNDERSTAT_LEAGUES:
        subsection(lk)

        p_r = passing_raw.get(f"fbref_passing_{lk}", {})
        m_r = misc_raw.get(f"fbref_misc_{lk}", {})

        if p_r.get("status") != "OK":
            print(f"    ❌ Passing failed: {p_r.get('error')}")
            results[lk] = {"status": "FAIL"}
            continue

        passing = p_r["df"].copy()
        passing.columns = [c.lower() for c in passing.columns]
        cols_ok = check_columns(passing, REQUIRED_FBREF_COLS, "passing")
        vol_ok  = check_volume(passing, "passing rows", min_rows=300)
        check_nulls(passing, ["poss", "cmp", "att"], "passing")
        print_dataframe_info(passing, "passing")
        print(f"\n    Sample:")
        print_sample(passing, ["team", "poss", "cmp", "att"])

        misc_rows = 0
        if m_r.get("status") == "OK":
            misc = m_r["df"].copy()
            misc.columns = [c.lower() for c in misc.columns]
            check_volume(misc, "misc rows", min_rows=300)
            print_dataframe_info(misc, "misc")
            misc_rows = len(misc)
        else:
            print(f"    ⚠️  Misc failed: {m_r.get('error')}")

        results[lk] = {
            "status":       "PASS" if all([cols_ok, vol_ok]) else "WARN",
            "passing_rows": len(passing),
            "misc_rows":    misc_rows,
            "passing_df":   passing,
        }

    return results

# =============================================================================
# TEST 4 — CLUB ELO (parallel across teams)
# =============================================================================

def test_club_elo():
    test_teams = {
        "la_liga":        "Real Madrid",
        "premier_league": "Manchester City",
        "bundesliga":     "Bayern Munich",
        "serie_a":        "Inter",
        "ligue_1":        "Paris Saint-Germain",
    }

    tasks = [
        {
            "key":     f"elo_{lk}",
            "label":   f"ClubElo/{team}",
            "timeout": TIMEOUTS["club_elo"],
            "fn":      (lambda t: lambda: sd.ClubElo().read_by_club(t).reset_index())(team),
        }
        for lk, team in test_teams.items()
    ]

    raw = run_parallel(tasks, "TEST 4 — CLUB ELO")

    section("TEST 4 — CLUB ELO ANALYSIS")
    results = {}

    for lk, team in test_teams.items():
        subsection(f"{lk} — {team}")
        r = raw.get(f"elo_{lk}", {})

        if r.get("status") != "OK":
            print(f"    ❌ Failed: {r.get('error')}")
            results[lk] = {"status": "FAIL"}
            continue

        elo_df = r["df"].copy()
        elo_df.columns = [c.lower() for c in elo_df.columns]
        cols_ok = check_columns(elo_df, REQUIRED_ELO_COLS, "elo")
        check_volume(elo_df, "elo rows", min_rows=10)
        print_dataframe_info(elo_df, "elo")

        if "date" in elo_df.columns:
            elo_2023 = elo_df[
                (elo_df["date"] >= "2022-08-01") &
                (elo_df["date"] <= "2023-06-30")
            ]
            if not elo_2023.empty:
                latest = elo_2023.iloc[-1]
                print(f"\n    ✅ Latest 2023 Elo for {team}: {latest.get('elo', 'N/A'):.0f}")

        results[lk] = {
            "status": "PASS" if cols_ok else "WARN",
            "rows":   len(elo_df)
        }

    return results

# =============================================================================
# TEST 5 — CROSS-SOURCE JOIN
# =============================================================================

def test_cross_join(understat_results, espn_results):
    section("TEST 5 — CROSS-SOURCE JOIN (Understat ↔ ESPN)")

    for league_key in UNDERSTAT_LEAGUES.keys():
        subsection(league_key)

        ud = understat_results.get(league_key, {})
        es = espn_results.get(league_key, {})

        if ud.get("status") == "FAIL" or es.get("status") == "FAIL":
            print(f"    ⚠️  Skipping — one or both sources failed")
            continue

        try:
            matches_df = ud["matches_df"].copy()
            lineups_df = es["lineups_df"].copy()

            matches_df["date"] = pd.to_datetime(
                matches_df["date"]
            ).dt.strftime("%Y-%m-%d")

            if "game" in lineups_df.columns:
                lineups_df["date_str"] = lineups_df["game"].apply(
                    lambda x: str(x).split(" ")[0] if pd.notna(x) else None
                )
            elif "date" in lineups_df.columns:
                lineups_df["date_str"] = pd.to_datetime(
                    lineups_df["date"]
                ).dt.strftime("%Y-%m-%d")

            ud_dates    = set(matches_df["date"].unique())
            es_dates    = set(lineups_df["date_str"].dropna().unique())
            overlap     = ud_dates & es_dates
            overlap_pct = len(overlap) / len(ud_dates) * 100 if ud_dates else 0

            print(f"    Understat dates  : {len(ud_dates)}")
            print(f"    ESPN dates       : {len(es_dates)}")
            print(f"    Overlap          : {len(overlap)} ({overlap_pct:.1f}%)")
            print(f"    Understat only   : {len(ud_dates - es_dates)}")
            print(f"    ESPN only        : {len(es_dates - ud_dates)}")

            icon = "✅" if overlap_pct >= 90 else "⚠️ " if overlap_pct >= 70 else "❌"
            print(f"\n    {icon} JOIN {'VIABLE' if overlap_pct >= 90 else 'PARTIAL' if overlap_pct >= 70 else 'PROBLEMATIC'} — {overlap_pct:.1f}% date overlap")

            ud_teams   = set(matches_df["home_team"].unique()) | set(matches_df["away_team"].unique())
            es_teams   = set(lineups_df["team"].unique()) if "team" in lineups_df.columns else set()
            team_pct   = len(ud_teams & es_teams) / len(ud_teams) * 100 if ud_teams else 0

            print(f"\n    Understat teams  : {len(ud_teams)}")
            print(f"    ESPN teams       : {len(es_teams)}")
            print(f"    Match rate       : {team_pct:.1f}%")

            if team_pct < 80:
                mismatched = sorted(list(ud_teams - es_teams))
                print(f"    ⚠️  Teams needing name normalisation:")
                for t in mismatched[:10]:
                    print(f"          → {t}")
            else:
                print(f"    ✅ Team names consistent")

        except Exception as e:
            print(f"    ❌ Cross-join failed: {e}")
            traceback.print_exc()

# =============================================================================
# SUMMARY
# =============================================================================

def print_summary(understat_r, espn_r, fbref_r, elo_r):
    section("FINAL SUMMARY")

    leagues = list(UNDERSTAT_LEAGUES.keys())
    sources = {
        "Understat": understat_r,
        "ESPN":      espn_r,
        "FBref":     fbref_r,
        "Club Elo":  elo_r,
    }

    print(f"  {'League':<22}" + "".join(f"{s:<16}" for s in sources.keys()))
    print(f"  {'-'*20}" + "".join(f"{'-'*15} " for _ in sources))

    all_pass = True
    for league in leagues:
        row = f"  {league:<22}"
        for source, results in sources.items():
            status = results.get(league, {}).get("status", "N/A")
            if status not in ("PASS", "N/A"):
                all_pass = False
            icon = "✅ PASS  " if status == "PASS" else \
                   "⚠️  WARN  " if status == "WARN" else \
                   "❌ FAIL  " if status == "FAIL" else \
                   "➖ N/A   "
            row += f"{icon:<16}"
        print(row)

    print()
    if all_pass:
        print("  ✅ ALL SOURCES PASSED — safe to build scrapers")
    else:
        print("  ⚠️  Some sources need attention — review above before building scrapers")

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*65)
    print("  SOCCERDATA FULL SOURCE VALIDATION — PARALLEL")
    print(f"  Season   : {SEASON}")
    print(f"  Leagues  : All 5 in parallel ({MAX_WORKERS} workers)")
    print(f"  Sources  : Understat, ESPN, FBref, Club Elo")
    print(f"  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    # Comment this out on reruns to use cached Understat data
    clear_cache()

    understat_results = test_understat()
    espn_results      = test_espn()
    fbref_results     = test_fbref()
    elo_results       = test_club_elo()

    test_cross_join(understat_results, espn_results)
    print_summary(understat_results, espn_results, fbref_results, elo_results)

    TIMER.print_report()

    print(f"\n  Finished : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total    : {TIMER.total():.1f}s")
    print("="*65 + "\n")