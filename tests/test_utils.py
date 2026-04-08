# =============================================================================
# PIPELINE UTILS — normalize_name() TESTS
# =============================================================================
# Validates that normalize_name() produces identical canonical strings for
# both the Understat and ESPN spelling of every team name that mismatches
# in the 2023 season validation run.
#
# Ground truth: actual team names extracted from soccerdata cache
# (tests/validate_sources.py cross-join output, confirmed April 2026).
#
# Bundesliga has the most cases (11 of 18 teams mismatch — 38.9% raw rate).
# =============================================================================

import io
import sys
import time

from pipeline.utils import PipelineTimer, normalize_name


def _assert_same(name_a: str, name_b: str, note: str = ""):
    """Assert that two raw names produce the same canonical output."""
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    assert a == b, (
        f"normalize_name mismatch{' — ' + note if note else ''}:\n"
        f"  '{name_a}' → '{a}'\n"
        f"  '{name_b}' → '{b}'"
    )


def _assert_output(raw: str, expected: str):
    """Assert that a raw name produces a specific canonical string."""
    result = normalize_name(raw)
    assert result == expected, (
        f"normalize_name('{raw}') = '{result}', expected '{expected}'"
    )


# =============================================================================
# La Liga
# =============================================================================

def test_la_liga_accents():
    """Accented chars are stripped — Understat already uses ASCII, ESPN uses accents."""
    print("\nTEST — La Liga accents")

    # Understat raw = Alaves; ESPN raw = Alavés
    _assert_same("Alaves", "Alavés",
                 "Alaves / Alavés")
    _assert_same("Almeria", "Almería",
                 "Almeria / Almería")
    _assert_same("Atletico Madrid", "Atlético Madrid",
                 "Atletico Madrid / Atlético Madrid")
    _assert_same("Cadiz", "Cádiz",
                 "Cadiz / Cádiz")

    print("   PASS — 4 La Liga accent pairs normalise correctly")


def test_la_liga_statsbomb_deportivo():
    """StatsBomb uses 'Deportivo Alavés' — must map to canonical 'alaves'."""
    print("\nTEST — La Liga StatsBomb Deportivo Alavés")
    _assert_output("Deportivo Alavés", "alaves")
    _assert_same("Deportivo Alavés", "Alavés",
                 "StatsBomb vs ESPN Alavés")
    print("   PASS — 'Deportivo Alavés' → 'alaves'")


# =============================================================================
# Premier League
# =============================================================================

def test_premier_league_short_vs_full():
    """ESPN uses full legal names; Understat uses common short names."""
    print("\nTEST — Premier League short vs full names")

    cases = [
        ("Bournemouth",           "AFC Bournemouth"),
        ("Brighton",              "Brighton & Hove Albion"),
        ("Luton",                 "Luton Town"),
        ("Tottenham",             "Tottenham Hotspur"),
        ("West Ham",              "West Ham United"),
    ]
    for understat_name, espn_name in cases:
        _assert_same(understat_name, espn_name,
                     f"{understat_name!r} vs ESPN {espn_name!r}")

    print(f"   PASS — {len(cases)} Premier League pairs normalise correctly")


# =============================================================================
# Bundesliga (priority — 11 of 18 teams mismatch)
# =============================================================================

def test_bundesliga_prefix_stripping():
    """ESPN uses FC/SC/VfL/VfB/SV/TSG prefixes; Understat strips them."""
    print("\nTEST — Bundesliga prefix mismatches")

    cases = [
        ("Augsburg",        "FC Augsburg",        "augsburg"),
        ("Bochum",          "VfL Bochum",         "bochum"),
        ("Freiburg",        "SC Freiburg",         "freiburg"),
        ("Hoffenheim",      "TSG Hoffenheim",      "hoffenheim"),
        ("Wolfsburg",       "VfL Wolfsburg",       "wolfsburg"),
    ]
    for understat_name, espn_name, expected in cases:
        _assert_same(understat_name, espn_name,
                     f"{understat_name!r} vs ESPN {espn_name!r}")
        _assert_output(understat_name, expected)
        _assert_output(espn_name, expected)

    print(f"   PASS — {len(cases)} Bundesliga prefix pairs normalise correctly")


def test_bundesliga_number_and_suffix():
    """Teams with leading numbers or year suffixes in their names."""
    print("\nTEST — Bundesliga number / suffix mismatches")

    # Darmstadt: ESPN has "SV Darmstadt 98", Understat has "Darmstadt"
    _assert_same("Darmstadt", "SV Darmstadt 98", "Darmstadt")
    _assert_output("SV Darmstadt 98", "darmstadt")

    # Heidenheim: ESPN "1. FC Heidenheim 1846", Understat "FC Heidenheim"
    _assert_same("FC Heidenheim", "1. FC Heidenheim 1846", "Heidenheim")
    _assert_output("1. FC Heidenheim 1846", "heidenheim")
    _assert_output("FC Heidenheim", "heidenheim")

    # Union Berlin: ESPN "1. FC Union Berlin", Understat "Union Berlin"
    _assert_same("Union Berlin", "1. FC Union Berlin", "Union Berlin")
    _assert_output("1. FC Union Berlin", "union berlin")

    # Mainz: Understat "Mainz 05", ESPN "Mainz"
    _assert_same("Mainz 05", "Mainz", "Mainz 05 vs Mainz")
    _assert_output("Mainz 05", "mainz")
    _assert_output("Mainz", "mainz")

    print("   PASS — 4 Bundesliga number/suffix pairs normalise correctly")


def test_bundesliga_gladbach():
    """Gladbach has both a punctuation difference and an accent."""
    print("\nTEST — Bundesliga Gladbach (punctuation + accent)")

    # Understat: "Borussia M.Gladbach"
    # ESPN: "Borussia Mönchengladbach" → after unidecode: "Borussia Monchengladbach"
    _assert_same("Borussia M.Gladbach", "Borussia Mönchengladbach",
                 "Gladbach forms")
    _assert_output("Borussia M.Gladbach", "borussia mgladbach")
    _assert_output("Borussia Mönchengladbach", "borussia mgladbach")

    print("   PASS — Gladbach all forms → 'borussia mgladbach'")


def test_bundesliga_leipzig():
    """RB Leipzig: Understat uses full legal name, ESPN uses abbreviation."""
    print("\nTEST — Bundesliga RB Leipzig (abbreviation)")

    # Understat: "RasenBallsport Leipzig"
    # ESPN: "RB Leipzig"
    _assert_same("RasenBallsport Leipzig", "RB Leipzig", "Leipzig")
    _assert_output("RasenBallsport Leipzig", "rb leipzig")
    _assert_output("RB Leipzig", "rb leipzig")

    print("   PASS — 'RasenBallsport Leipzig' and 'RB Leipzig' both → 'rb leipzig'")


def test_bundesliga_stable_names():
    """Teams whose names already match between Understat and ESPN."""
    print("\nTEST — Bundesliga stable names (no correction needed)")

    stable = [
        "Bayern Munich",
        "Bayer Leverkusen",
        "Borussia Dortmund",
        "Eintracht Frankfurt",
        "FC Cologne",
        "Werder Bremen",
        "VfB Stuttgart",
    ]
    for name in stable:
        result = normalize_name(name)
        # Should just be lowercased — no correction applied
        assert result == name.lower().strip(), \
            f"Stable name '{name}' was incorrectly modified → '{result}'"

    print(f"   PASS — {len(stable)} stable Bundesliga names unchanged")


# =============================================================================
# Serie A
# =============================================================================

def test_serie_a_name_differences():
    """Inter, Roma, Verona all use different forms in ESPN vs Understat."""
    print("\nTEST — Serie A name differences")

    cases = [
        ("Inter",   "Internazionale",  "inter"),
        ("Roma",    "AS Roma",         "roma"),
        ("Verona",  "Hellas Verona",   "verona"),
    ]
    for understat_name, espn_name, expected in cases:
        _assert_same(understat_name, espn_name,
                     f"{understat_name!r} vs ESPN {espn_name!r}")
        _assert_output(understat_name, expected)
        _assert_output(espn_name, expected)

    print(f"   PASS — {len(cases)} Serie A pairs normalise correctly")


# =============================================================================
# Ligue 1
# =============================================================================

def test_ligue_1_prefix_and_suffix():
    """Monaco, Le Havre, Reims, Rennes all have prefix/suffix differences."""
    print("\nTEST — Ligue 1 prefix / suffix / Stade variants")

    cases = [
        ("Monaco",              "AS Monaco",        "monaco"),
        ("Le Havre",            "Le Havre AC",      "le havre"),
        ("Reims",               "Stade de Reims",   "reims"),
        ("Rennes",              "Stade Rennais",    "rennes"),
    ]
    for understat_name, espn_name, expected in cases:
        _assert_same(understat_name, espn_name,
                     f"{understat_name!r} vs ESPN {espn_name!r}")
        _assert_output(understat_name, expected)
        _assert_output(espn_name, expected)

    print(f"   PASS — {len(cases)} Ligue 1 pairs normalise correctly")


def test_ligue_1_psg_hyphen():
    """PSG: Understat uses space, ESPN uses hyphen."""
    print("\nTEST — Ligue 1 Paris Saint-Germain hyphen")

    _assert_same("Paris Saint Germain", "Paris Saint-Germain", "PSG")
    _assert_output("Paris Saint Germain", "paris saint germain")
    _assert_output("Paris Saint-Germain", "paris saint germain")

    print("   PASS — Both PSG forms → 'paris saint germain'")


# =============================================================================
# Idempotency
# =============================================================================

def test_idempotency():
    """normalize_name applied twice returns the same result as once."""
    print("\nTEST — Idempotency")

    names = [
        "Atlético Madrid",
        "RasenBallsport Leipzig",
        "Borussia Mönchengladbach",
        "Paris Saint-Germain",
        "Tottenham Hotspur",
        "1. FC Heidenheim 1846",
        "Real Madrid",
    ]
    for name in names:
        once  = normalize_name(name)
        twice = normalize_name(once)
        assert once == twice, \
            f"normalize_name is not idempotent for '{name}': once='{once}', twice='{twice}'"

    print(f"   PASS — {len(names)} names are idempotent")


# =============================================================================
# PipelineTimer
# =============================================================================

def test_pipeline_timer_start_stop_records_elapsed():
    """start/stop records a positive elapsed time for a label."""
    print("\nTEST — PipelineTimer start/stop records elapsed time")

    timer = PipelineTimer()
    timer.start("step_a")
    time.sleep(0.05)          # 50 ms — well within any CI runner tolerance
    elapsed = timer.stop("step_a")

    assert elapsed >= 0.04, f"Elapsed too short: {elapsed:.4f}s"
    assert elapsed < 5.0,   f"Elapsed suspiciously long: {elapsed:.4f}s"

    timings = timer.to_dict()
    assert "step_a" in timings, "step_a not found in to_dict() output"
    assert abs(timings["step_a"] - elapsed) < 0.001, "to_dict value differs from stop() return"

    print(f"   PASS — elapsed={elapsed:.3f}s, to_dict key present")


def test_pipeline_timer_multiple_labels():
    """Multiple independent labels are all recorded correctly."""
    print("\nTEST — PipelineTimer multiple labels")

    timer = PipelineTimer()
    for label in ("alpha", "beta", "gamma"):
        timer.start(label)
        time.sleep(0.01)
        timer.stop(label)

    d = timer.to_dict()
    assert set(d.keys()) == {"alpha", "beta", "gamma"}, f"Unexpected keys: {d.keys()}"
    for label, secs in d.items():
        assert secs >= 0.005, f"'{label}' elapsed too short: {secs:.4f}s"

    print(f"   PASS — 3 labels recorded: {list(d.keys())}")


def test_pipeline_timer_stop_without_start_raises():
    """Stopping a label that was never started raises KeyError."""
    print("\nTEST — PipelineTimer stop without start raises KeyError")

    timer = PipelineTimer()
    try:
        timer.stop("never_started")
        assert False, "Expected KeyError was not raised"
    except KeyError:
        pass

    print("   PASS — KeyError raised as expected")


def test_pipeline_timer_summary_prints_without_error():
    """summary() writes output to stdout without raising."""
    print("\nTEST — PipelineTimer summary() prints without error")

    timer = PipelineTimer()
    timer.start("s1")
    time.sleep(0.01)
    timer.stop("s1")
    timer.start("s2")
    time.sleep(0.01)
    timer.stop("s2")

    # Capture stdout to verify it contains expected strings
    captured = io.StringIO()
    sys.stdout = captured
    try:
        timer.summary()
    finally:
        sys.stdout = sys.__stdout__

    output = captured.getvalue()
    assert "PIPELINE TIMING SUMMARY" in output, "Header missing from summary output"
    assert "TOTAL" in output, "'TOTAL' line missing from summary output"
    assert "s1" in output, "'s1' label missing from summary output"
    assert "s2" in output, "'s2' label missing from summary output"

    print("   PASS — summary() printed correctly")


def test_pipeline_timer_summary_empty():
    """summary() on a fresh timer prints a no-timings message without error."""
    print("\nTEST — PipelineTimer summary() with no timings")

    timer = PipelineTimer()
    captured = io.StringIO()
    sys.stdout = captured
    try:
        timer.summary()
    finally:
        sys.stdout = sys.__stdout__

    output = captured.getvalue()
    assert "PIPELINE TIMING SUMMARY" in output
    assert "no timings" in output.lower()

    print("   PASS — empty summary printed cleanly")


def test_pipeline_timer_to_dict_expected_keys():
    """to_dict() returns exactly the labels that were stopped."""
    print("\nTEST — PipelineTimer to_dict() returns expected keys")

    timer = PipelineTimer()
    labels = ["understat_matches", "understat_player_stats", "espn_lineups", "bq_load"]
    for lbl in labels:
        timer.start(lbl)
        timer.stop(lbl)

    d = timer.to_dict()
    assert set(d.keys()) == set(labels), f"Key mismatch: {set(d.keys())} != {set(labels)}"
    for lbl in labels:
        assert isinstance(d[lbl], float), f"'{lbl}' value is not float: {type(d[lbl])}"

    print(f"   PASS — to_dict() returned {len(labels)} float-valued keys")


if __name__ == "__main__":
    print("=" * 60)
    print("  normalize_name() — SMOKE TESTS")
    print("=" * 60)

    test_la_liga_accents()
    test_la_liga_statsbomb_deportivo()
    test_premier_league_short_vs_full()
    test_bundesliga_prefix_stripping()
    test_bundesliga_number_and_suffix()
    test_bundesliga_gladbach()
    test_bundesliga_leipzig()
    test_bundesliga_stable_names()
    test_serie_a_name_differences()
    test_ligue_1_prefix_and_suffix()
    test_ligue_1_psg_hyphen()
    test_idempotency()

    print("\n" + "=" * 60)
    print("  PipelineTimer — SMOKE TESTS")
    print("=" * 60)

    test_pipeline_timer_start_stop_records_elapsed()
    test_pipeline_timer_multiple_labels()
    test_pipeline_timer_stop_without_start_raises()
    test_pipeline_timer_summary_prints_without_error()
    test_pipeline_timer_summary_empty()
    test_pipeline_timer_to_dict_expected_keys()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
