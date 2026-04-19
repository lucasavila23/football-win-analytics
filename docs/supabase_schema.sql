-- =============================================================================
-- Football Analytics — Supabase Schema
-- Run this once in the Supabase SQL Editor before the first sync.
-- All tables are append-ready; the Python sync uses UPSERT with the
-- UNIQUE constraints below for idempotency.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- mart_league_standings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart_league_standings (
    team                  TEXT        NOT NULL,
    league                TEXT        NOT NULL,
    season                TEXT        NOT NULL,
    matches_played        INTEGER,
    wins                  INTEGER,
    draws                 INTEGER,
    losses                INTEGER,
    points                INTEGER,
    goals_for             INTEGER,
    goals_against         INTEGER,
    goal_difference       INTEGER,
    total_xg_for          FLOAT8,
    total_xg_against      FLOAT8,
    total_xg_difference   FLOAT8,
    avg_ppda              FLOAT8,
    avg_deep_completions  FLOAT8,
    win_rate              FLOAT8,
    CONSTRAINT mart_league_standings_pk UNIQUE (team, league, season)
);

-- ---------------------------------------------------------------------------
-- mart_winning_profiles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart_winning_profiles (
    league                          TEXT        NOT NULL,
    season                          TEXT        NOT NULL,
    match_result                    TEXT        NOT NULL,
    is_home                         BOOLEAN     NOT NULL,
    matches                         INTEGER,
    avg_goals_scored                FLOAT8,
    avg_goals_conceded              FLOAT8,
    avg_xg_for                      FLOAT8,
    avg_xg_against                  FLOAT8,
    avg_xg_diff                     FLOAT8,
    avg_np_xg_for                   FLOAT8,
    avg_np_xg_against               FLOAT8,
    avg_ppda                        FLOAT8,
    avg_opponent_ppda               FLOAT8,
    avg_ppda_diff                   FLOAT8,
    avg_deep_completions            FLOAT8,
    avg_opponent_deep_completions   FLOAT8,
    stddev_xg_for                   FLOAT8,
    stddev_ppda                     FLOAT8,
    CONSTRAINT mart_winning_profiles_pk UNIQUE (league, season, match_result, is_home)
);

-- ---------------------------------------------------------------------------
-- mart_player_performance
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart_player_performance (
    player_name         TEXT        NOT NULL,
    team                TEXT        NOT NULL,
    league              TEXT        NOT NULL,
    season              TEXT        NOT NULL,
    match_appearances   INTEGER,
    total_minutes       INTEGER,
    total_goals         INTEGER,
    total_assists       INTEGER,
    total_own_goals     INTEGER,
    total_shots         INTEGER,
    total_xg            FLOAT8,
    total_xa            FLOAT8,
    total_xg_chain      FLOAT8,
    total_xg_buildup    FLOAT8,
    xg_per_90           FLOAT8,
    goals_per_90        FLOAT8,
    total_key_passes    INTEGER,
    total_yellow_cards  INTEGER,
    total_red_cards     INTEGER,
    primary_position    TEXT,
    CONSTRAINT mart_player_performance_pk UNIQUE (player_name, team, league, season)
);

-- ---------------------------------------------------------------------------
-- mart_tactical_analysis
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart_tactical_analysis (
    team                    TEXT    NOT NULL,
    league                  TEXT    NOT NULL,
    season                  TEXT    NOT NULL,
    matches_played          INTEGER,
    avg_ppda                FLOAT8,
    best_ppda               FLOAT8,
    worst_ppda              FLOAT8,
    ppda_consistency        FLOAT8,
    avg_opponent_ppda       FLOAT8,
    avg_deep_completions    FLOAT8,
    total_deep_completions  FLOAT8,
    avg_xg_for              FLOAT8,
    avg_np_xg_for           FLOAT8,
    wins                    INTEGER,
    win_rate                FLOAT8,
    CONSTRAINT mart_tactical_analysis_pk UNIQUE (team, league, season)
);

-- ---------------------------------------------------------------------------
-- mart_team_comparison
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart_team_comparison (
    team                  TEXT    NOT NULL,
    league                TEXT    NOT NULL,
    season                TEXT    NOT NULL,
    matches_played        INTEGER,
    wins                  INTEGER,
    draws                 INTEGER,
    losses                INTEGER,
    points                INTEGER,
    goals_for             INTEGER,
    goals_against         INTEGER,
    goal_difference       INTEGER,
    total_xg_for          FLOAT8,
    total_xg_against      FLOAT8,
    avg_xg_for            FLOAT8,
    avg_xg_against        FLOAT8,
    avg_ppda              FLOAT8,
    avg_deep_completions  FLOAT8,
    win_rate              FLOAT8,
    xg_for_z              FLOAT8,
    ppda_z                FLOAT8,
    deep_completions_z    FLOAT8,
    CONSTRAINT mart_team_comparison_pk UNIQUE (team, league, season)
);

-- ---------------------------------------------------------------------------
-- mart_head_to_head
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart_head_to_head (
    team_a                  TEXT    NOT NULL,
    team_b                  TEXT    NOT NULL,
    league                  TEXT    NOT NULL,
    season                  TEXT    NOT NULL,
    matches_played          INTEGER,
    team_a_wins             INTEGER,
    draws                   INTEGER,
    team_b_wins             INTEGER,
    team_a_goals            INTEGER,
    team_b_goals            INTEGER,
    team_a_goal_difference  INTEGER,
    team_a_avg_xg           FLOAT8,
    team_b_avg_xg           FLOAT8,
    team_a_win_rate         FLOAT8,
    team_b_win_rate         FLOAT8,
    CONSTRAINT mart_head_to_head_pk UNIQUE (team_a, team_b, league, season)
);

-- ---------------------------------------------------------------------------
-- Row Level Security — enable read-only public access for the frontend.
-- The sync script uses the service_role key which bypasses RLS.
-- ---------------------------------------------------------------------------
ALTER TABLE mart_league_standings    ENABLE ROW LEVEL SECURITY;
ALTER TABLE mart_winning_profiles    ENABLE ROW LEVEL SECURITY;
ALTER TABLE mart_player_performance  ENABLE ROW LEVEL SECURITY;
ALTER TABLE mart_tactical_analysis   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mart_team_comparison     ENABLE ROW LEVEL SECURITY;
ALTER TABLE mart_head_to_head        ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read" ON mart_league_standings    FOR SELECT USING (true);
CREATE POLICY "Public read" ON mart_winning_profiles    FOR SELECT USING (true);
CREATE POLICY "Public read" ON mart_player_performance  FOR SELECT USING (true);
CREATE POLICY "Public read" ON mart_tactical_analysis   FOR SELECT USING (true);
CREATE POLICY "Public read" ON mart_team_comparison     FOR SELECT USING (true);
CREATE POLICY "Public read" ON mart_head_to_head        FOR SELECT USING (true);
