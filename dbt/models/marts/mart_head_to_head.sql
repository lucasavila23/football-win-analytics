-- =============================================================================
-- mart_head_to_head
-- =============================================================================
-- Historical head-to-head record between every pair of teams.
-- Sourced from int_head_to_head (season-level aggregation already done there).
--
-- One row per (team_a, team_b, league, season) where team_a < team_b
-- alphabetically (canonical ordering to avoid duplicate pairs).
--
-- Used by the Lovable frontend for the rivalry view.
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    team_a,
    team_b,
    league,
    season,

    matches_played,
    team_a_wins,
    draws,
    team_b_wins,

    team_a_goals,
    team_b_goals,
    team_a_goals - team_b_goals                AS team_a_goal_difference,

    ROUND(team_a_avg_xg, 3)                    AS team_a_avg_xg,
    ROUND(team_b_avg_xg, 3)                    AS team_b_avg_xg,

    ROUND(
        {{ calculate_win_rate('team_a_wins', 'matches_played') }},
        3
    )                                          AS team_a_win_rate,

    ROUND(
        {{ calculate_win_rate('team_b_wins', 'matches_played') }},
        3
    )                                          AS team_b_win_rate

FROM {{ ref('int_head_to_head') }}
ORDER BY league, season, matches_played DESC
