# =============================================================================
# PIPELINE UTILITIES
# =============================================================================
# Shared helpers used across scrapers, loaders, dbt macros, and tests.
#
# normalize_name(name) — canonical team name for Understat ↔ ESPN joins.
#
# WHY THIS EXISTS:
#   Understat and ESPN use different team name conventions. Joining on raw
#   names silently drops rows. Bundesliga is the worst case: only 38.9% of
#   names match without normalisation.
#
# ALGORITHM:
#   1. unidecode  — strips accents (Atlético → Atletico, Alavés → Alaves)
#   2. lowercase + strip whitespace
#   3. _CORRECTIONS lookup — handles prefix differences (VfL Wolfsburg →
#      wolfsburg), name contractions (Internazionale → inter), and all
#      other cases that unidecode alone cannot fix
#
# CANONICAL FORMS (the output this function always returns):
#   We use the shorter / more common form as canonical.
#   Full mapping is documented in each league block below.
#
# COVERAGE: La Liga, Premier League, Bundesliga, Serie A, Ligue 1.
# StatsBomb team name variants are included where they differ from
# the Understat/ESPN canonical.
# =============================================================================

import time

from unidecode import unidecode

# -----------------------------------------------------------------------------
# Corrections dict
# -----------------------------------------------------------------------------
# Keys:   lowercased, unidecoded team name (as it arrives after step 2)
# Values: canonical form (also lowercase)
#
# Entries are grouped by league for readability.
# Only mismatches that survive unidecode are listed here.
# -----------------------------------------------------------------------------

_CORRECTIONS: dict[str, str] = {

    # ── La Liga ───────────────────────────────────────────────────────────────
    # After unidecode, all La Liga names already match between Understat and
    # ESPN for the 2023 season. The StatsBomb open data uses the full club
    # name for Alavés ("Deportivo Alavés") which needs stripping.
    "deportivo alaves":             "alaves",

    # ── Premier League ────────────────────────────────────────────────────────
    # ESPN uses full legal names; Understat uses common short names.
    "afc bournemouth":              "bournemouth",
    "brighton & hove albion":       "brighton",
    "brighton and hove albion":     "brighton",   # in case & is written as "and"
    "luton town":                   "luton",
    "tottenham hotspur":            "tottenham",
    "west ham united":              "west ham",

    # ── Bundesliga ────────────────────────────────────────────────────────────
    # 11 of 18 teams mismatch (38.9% raw match rate confirmed in validation).
    # Understat tends to use short common names; ESPN uses full official names.

    # Augsburg: ESPN "FC Augsburg" → canonical "augsburg"
    "fc augsburg":                  "augsburg",

    # Bochum: ESPN "VfL Bochum" → canonical "bochum"
    "vfl bochum":                   "bochum",

    # Gladbach: Understat "Borussia M.Gladbach", ESPN "Borussia Mönchengladbach"
    # After unidecode, ESPN becomes "Borussia Monchengladbach"
    "borussia m.gladbach":          "borussia mgladbach",
    "borussia monchengladbach":     "borussia mgladbach",

    # Darmstadt: ESPN "SV Darmstadt 98" → canonical "darmstadt"
    "sv darmstadt 98":              "darmstadt",

    # Heidenheim: Understat "FC Heidenheim", ESPN "1. FC Heidenheim 1846"
    "fc heidenheim":                "heidenheim",
    "1. fc heidenheim 1846":        "heidenheim",

    # Freiburg: ESPN "SC Freiburg" → canonical "freiburg"
    "sc freiburg":                  "freiburg",

    # Hoffenheim: ESPN "TSG Hoffenheim" → canonical "hoffenheim"
    "tsg hoffenheim":               "hoffenheim",

    # Mainz: Understat "Mainz 05", ESPN "Mainz" → canonical "mainz"
    "mainz 05":                     "mainz",

    # Leipzig: Understat "RasenBallsport Leipzig", ESPN "RB Leipzig"
    # After unidecode, Understat becomes "rasenballsport leipzig"
    "rasenballsport leipzig":       "rb leipzig",

    # Union Berlin: ESPN "1. FC Union Berlin" → canonical "union berlin"
    "1. fc union berlin":           "union berlin",

    # Wolfsburg: ESPN "VfL Wolfsburg" → canonical "wolfsburg"
    "vfl wolfsburg":                "wolfsburg",

    # ── Serie A ───────────────────────────────────────────────────────────────
    # Three mismatches: short vs full vs local name.

    # Inter: ESPN "Internazionale" → canonical "inter"
    "internazionale":               "inter",

    # Roma: ESPN "AS Roma" → canonical "roma"
    "as roma":                      "roma",

    # Verona: ESPN "Hellas Verona" → canonical "verona"
    "hellas verona":                "verona",

    # ── Ligue 1 ───────────────────────────────────────────────────────────────
    # Five mismatches: AS prefix, hyphen, Stade prefix, and AC suffix.

    # Monaco: ESPN "AS Monaco" → canonical "monaco"
    "as monaco":                    "monaco",

    # PSG: ESPN uses hyphen "Paris Saint-Germain", Understat uses space
    # After unidecode, hyphen remains → map to space version
    "paris saint-germain":          "paris saint germain",

    # Reims: ESPN "Stade de Reims" → canonical "reims"
    "stade de reims":               "reims",

    # Rennes: ESPN "Stade Rennais" → canonical "rennes"
    "stade rennais":                "rennes",

    # Le Havre: ESPN "Le Havre AC" → canonical "le havre"
    "le havre ac":                  "le havre",
}


def normalize_name(name: str) -> str:
    """
    Return the canonical team name for cross-source joins.

    Applies three normalisation steps:
      1. unidecode — strips accented characters (Atlético → Atletico)
      2. lowercase + strip whitespace
      3. _CORRECTIONS dict — resolves prefix/suffix/contraction differences

    This function is idempotent: normalize_name(normalize_name(x)) == normalize_name(x).

    Args:
        name: Raw team name from any source (Understat, ESPN, StatsBomb, etc.)

    Returns:
        Normalised string, always lowercase.

    Examples:
        normalize_name("Atlético Madrid")       → "atletico madrid"
        normalize_name("VfL Wolfsburg")         → "wolfsburg"
        normalize_name("RasenBallsport Leipzig") → "rb leipzig"
        normalize_name("Tottenham Hotspur")      → "tottenham"
        normalize_name("Internazionale")         → "inter"
        normalize_name("Paris Saint-Germain")    → "paris saint germain"
    """
    if not isinstance(name, str):
        return name

    # Step 1 — accent stripping
    normalised = unidecode(name)

    # Step 2 — lowercase + strip
    normalised = normalised.strip().lower()

    # Step 3 — corrections
    normalised = _CORRECTIONS.get(normalised, normalised)

    return normalised


# =============================================================================
# PipelineTimer
# =============================================================================
# Lightweight wall-clock timer used by main.py to record per-step latency.
#
# Usage pattern in main.py:
#   timer = PipelineTimer()
#   timer.start("understat_matches")
#   ... do work ...
#   timer.stop("understat_matches")
#   timer.summary()  # prints table to stdout
#   timer.to_dict()  # returns dict for JSON serialisation
#
# summary() always prints to stdout (not logger) so it appears in
# GitHub Actions logs when we wire up the pipeline.yml.
# =============================================================================


class PipelineTimer:
    """
    Named wall-clock timer for pipeline steps.

    Records start/stop pairs per label. Supports formatted table output
    (summary()) and dict serialisation (to_dict()) for saving timing JSON.
    """

    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self._timings: dict[str, float] = {}

    def start(self, label: str) -> None:
        """Start (or restart) the timer for the given label."""
        self._starts[label] = time.time()

    def stop(self, label: str) -> float:
        """
        Stop the timer for the given label and record elapsed seconds.

        Returns:
            Elapsed seconds as float.

        Raises:
            KeyError: if start() was never called for this label.
        """
        if label not in self._starts:
            raise KeyError(f"PipelineTimer: '{label}' was never started")
        elapsed = time.time() - self._starts.pop(label)
        self._timings[label] = elapsed
        return elapsed

    def summary(self) -> None:
        """Print a formatted timing table to stdout."""
        if not self._timings:
            print("\n  PIPELINE TIMING SUMMARY")
            print("  ========================")
            print("  (no timings recorded)")
            return

        col_width = max(len(label) for label in self._timings)
        col_width = max(col_width, 45)
        total = sum(self._timings.values())
        sep = "  " + "─" * (col_width + 12)

        print()
        print("  PIPELINE TIMING SUMMARY")
        print("  " + "=" * (col_width + 12))
        for label, seconds in self._timings.items():
            print(f"  {label:<{col_width}}  {seconds:.1f}s")
        print(sep)
        print(f"  {'TOTAL':<{col_width}}  {total:.1f}s")

    def to_dict(self) -> dict[str, float]:
        """Return all recorded timings as a plain dict."""
        return dict(self._timings)
