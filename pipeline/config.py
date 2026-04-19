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
    # champions_league excluded: Understat and ESPN do not cover UCL
}

# --- Seasons ---
CURRENT_SEASON = "2024"
HISTORICAL_SEASONS = [str(y) for y in range(2014, 2024)]  # 2014 → 2023
ALL_SEASONS = HISTORICAL_SEASONS + [CURRENT_SEASON]

# --- GCP ---
GCP_PROJECT_ID = "football-analytics-491123"       # Fill in after GCP setup
GCS_BUCKET_NAME = "football-analytics-raw-491123"    # Fill in after GCP setup
BIGQUERY_DATASET_RAW = "raw"
BIGQUERY_DATASET_STAGING = "staging"
BIGQUERY_DATASET_INTERMEDIATE = "intermediate"
BIGQUERY_DATASET_MARTS = "marts"

# --- Sources per league ---
# Controls which scrapers run for which leagues
SOURCES = {
    "understat": ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1"],
    "espn":      ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1"],
    # fbref was hard-blocked (403) — replaced by StatsBomb Open Data
    "statsbomb": ["la_liga", "premier_league", "bundesliga", "serie_a", "ligue_1"],
}

# --- StatsBomb Open Data coverage ---
# Maps (league_key, season_start_year) → StatsBomb competition_id + season_id.
# Only includes seasons that overlap with our Understat/ESPN seasons.
# Champions League excluded: open data has only 1 match per season (insufficient).
# Source: tests/validate_statsbomb.py output from Session 4.
STATSBOMB_SEASON_MAP: dict[tuple[str, str], dict] = {
    ("la_liga", "2014"): {"competition_id": 11, "season_id": 26,  "season_name": "2014/2015"},
    ("la_liga", "2015"): {"competition_id": 11, "season_id": 27,  "season_name": "2015/2016"},
    ("la_liga", "2016"): {"competition_id": 11, "season_id": 2,   "season_name": "2016/2017"},
    ("la_liga", "2017"): {"competition_id": 11, "season_id": 1,   "season_name": "2017/2018"},
    ("la_liga", "2018"): {"competition_id": 11, "season_id": 4,   "season_name": "2018/2019"},
    ("la_liga", "2019"): {"competition_id": 11, "season_id": 42,  "season_name": "2019/2020"},
    ("la_liga", "2020"): {"competition_id": 11, "season_id": 90,  "season_name": "2020/2021"},
    ("premier_league", "2015"): {"competition_id": 2,  "season_id": 27,  "season_name": "2015/2016"},
    ("bundesliga",     "2015"): {"competition_id": 9,  "season_id": 27,  "season_name": "2015/2016"},
    ("bundesliga",     "2023"): {"competition_id": 9,  "season_id": 281, "season_name": "2023/2024"},
    ("serie_a",        "2015"): {"competition_id": 12, "season_id": 27,  "season_name": "2015/2016"},
    ("ligue_1",        "2015"): {"competition_id": 7,  "season_id": 27,  "season_name": "2015/2016"},
    ("ligue_1",        "2021"): {"competition_id": 7,  "season_id": 108, "season_name": "2021/2022"},
    ("ligue_1",        "2022"): {"competition_id": 7,  "season_id": 235, "season_name": "2022/2023"},
}

# StatsBomb competition names used in sb.competition_events() calls
# Maps our league keys to the (country, division) args StatsBomb expects
STATSBOMB_COMPETITION_META: dict[str, dict[str, str]] = {
    "la_liga":        {"country": "Spain",   "division": "La Liga"},
    "premier_league": {"country": "England", "division": "Premier League"},
    "bundesliga":     {"country": "Germany", "division": "1. Bundesliga"},
    "serie_a":        {"country": "Italy",   "division": "Serie A"},
    "ligue_1":        {"country": "France",  "division": "Ligue 1"},
}