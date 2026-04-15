-- =============================================================================
-- int_winning_matches
-- =============================================================================
-- Filters int_team_match_aggregates to matches where the team won.
-- One row per winning team per match per league per season.
--
-- This is the foundation for mart_winning_profiles — all aggregations about
-- "what do winning teams look like" flow through here.
--
-- DEVELOPMENT: LIMIT 1000 active. Remove for production runs.
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    match_date,
    team,
    opponent,
    is_home,

    goals_scored,
    goals_conceded,

    xg_for,
    xg_against,
    np_xg_for,
    np_xg_against,

    ppda,
    opponent_ppda,
    deep_completions,
    opponent_deep_completions,

    match_result,
    points,
    xg_diff,
    score_diff,
    league,
    season

FROM {{ ref('int_team_match_aggregates') }}
WHERE match_result = 'win'
  AND season = '{{ var("target_season", "2023") }}'

LIMIT 1000
