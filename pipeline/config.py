# =============================================================================
# FOOTBALL ANALYTICS — CENTRAL CONFIGURATION
# =============================================================================

# --- Leagues ---
# soccerdata league identifiers
LEAGUES = {
    "la_liga":        "ESP-La Liga",
    "premier_league": "ENG-Premier League",
    "bundesliga":     "GER-Bundesliga",
    "serie_a":        "ITA-Serie A",
    "ligue_1":        "FRA-Ligue 1",
    "champions_league": "UEFA-Champions League",
}

# --- Seasons ---
CURRENT_SEASON = "2024"
HISTORICAL_SEASONS = [str(y) for y in range(2014, 2024)]  # 2014 → 2023
ALL_SEASONS = HISTORICAL_SEASONS + [CURRENT_SEASON]

# --- GCP ---
GCP_PROJECT_ID = "your-gcp-project-id"       # Fill in after GCP setup
GCS_BUCKET_NAME = "football-analytics-raw"    # Fill in after GCP setup
BIGQUERY_DATASET_RAW = "raw"
BIGQUERY_DATASET_STAGING = "staging"
BIGQUERY_DATASET_INTERMEDIATE = "intermediate"
BIGQUERY_DATASET_MARTS = "marts"

# --- Sources per league ---
# Controls which scrapers run for which leagues
SOURCES = {
    "understat": ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1"],
    "espn":      ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1"],
    "fbref":     ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1", "champions_league"],
}