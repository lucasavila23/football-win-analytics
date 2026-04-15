-- =============================================================================
-- int_team_match_aggregates
-- =============================================================================
-- One row per TEAM per MATCH per league per season.
--
-- Unpivots stg_matches (one row/match) into two rows per match:
--   one for the home team, one for the away team.
-- Each row carries the team's own metrics (xg_for, ppda, etc.) and the
-- opponent's metrics (xg_against, opponent_ppda, etc.).
--
-- Points are assigned per match (3 / 1 / 0) — sum over season gives standings.
--
-- NOTE: stg_player_stats has no match-level date/ID column, so player stats
-- cannot be joined here at match granularity. Seasonal player aggregations
-- are joined at mart level instead.
--
-- DEVELOPMENT: LIMIT 2000 active. Remove for production runs.
-- =============================================================================

{{ config(materialized='table') }}

-- Home team perspective
SELECT
    match_date,
    home_team                                           AS team,
    away_team                                           AS opponent,
    TRUE                                                AS is_home,

    home_score                                          AS goals_scored,
    away_score                                          AS goals_conceded,

    home_xg                                             AS xg_for,
    away_xg                                             AS xg_against,
    home_np_xg                                          AS np_xg_for,
    away_np_xg                                          AS np_xg_against,

    home_ppda                                           AS ppda,
    away_ppda                                           AS opponent_ppda,
    home_deep_completions                               AS deep_completions,
    away_deep_completions                               AS opponent_deep_completions,

    CASE
        WHEN home_score > away_score THEN 'win'
        WHEN home_score < away_score THEN 'loss'
        ELSE                              'draw'
    END                                                 AS match_result,

    CASE
        WHEN home_score > away_score THEN 3
        WHEN home_score = away_score THEN 1
        ELSE                              0
    END                                                 AS points,

    xg_diff,
    score_diff,
    league,
    season

FROM {{ ref('stg_matches') }}

UNION ALL

-- Away team perspective
SELECT
    match_date,
    away_team                                           AS team,
    home_team                                           AS opponent,
    FALSE                                               AS is_home,

    away_score                                          AS goals_scored,
    home_score                                          AS goals_conceded,

    away_xg                                             AS xg_for,
    home_xg                                             AS xg_against,
    away_np_xg                                          AS np_xg_for,
    home_np_xg                                          AS np_xg_against,

    away_ppda                                           AS ppda,
    home_ppda                                           AS opponent_ppda,
    away_deep_completions                               AS deep_completions,
    home_deep_completions                               AS opponent_deep_completions,

    CASE
        WHEN away_score > home_score THEN 'win'
        WHEN away_score < home_score THEN 'loss'
        ELSE                              'draw'
    END                                                 AS match_result,

    CASE
        WHEN away_score > home_score THEN 3
        WHEN away_score = home_score THEN 1
        ELSE                              0
    END                                                 AS points,

    -xg_diff                                            AS xg_diff,
    -score_diff                                         AS score_diff,
    league,
    season

FROM {{ ref('stg_matches') }}

LIMIT 2000
