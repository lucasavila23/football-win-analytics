-- =============================================================================
-- mart_winning_profiles
-- =============================================================================
-- THE CORE ANALYTICAL OUTPUT of the platform.
--
-- Answers: "What do winning teams look like, compared to drawing or losing teams?"
--
-- Aggregates match-level xG, pressing (PPDA), and carry metrics by:
--   league × season × match_result × is_home
--
-- Lower PPDA = better pressing (fewer passes allowed per defensive action).
-- Higher deep_completions = more penetration into dangerous areas.
-- xg_diff > 0 = team created more quality chances than it allowed.
--
-- One row per (league, season, match_result, is_home) combination.
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    league,
    season,
    match_result,
    is_home,

    COUNT(*)                                                    AS matches,

    -- Scoring
    ROUND(AVG(goals_scored),                    2)             AS avg_goals_scored,
    ROUND(AVG(goals_conceded),                  2)             AS avg_goals_conceded,

    -- xG
    ROUND(AVG(xg_for),                          3)             AS avg_xg_for,
    ROUND(AVG(xg_against),                      3)             AS avg_xg_against,
    ROUND(AVG(xg_for - xg_against),             3)             AS avg_xg_diff,
    ROUND(AVG(np_xg_for),                       3)             AS avg_np_xg_for,
    ROUND(AVG(np_xg_against),                   3)             AS avg_np_xg_against,

    -- Pressing (PPDA — lower = more intense press)
    ROUND(AVG(ppda),                            3)             AS avg_ppda,
    ROUND(AVG(opponent_ppda),                   3)             AS avg_opponent_ppda,
    ROUND(AVG(ppda) - AVG(opponent_ppda),       3)             AS avg_ppda_diff,

    -- Carry / penetration
    ROUND(AVG(deep_completions),                1)             AS avg_deep_completions,
    ROUND(AVG(opponent_deep_completions),       1)             AS avg_opponent_deep_completions,

    -- Std deviations for variance analysis
    ROUND(STDDEV(xg_for),                       3)             AS stddev_xg_for,
    ROUND(STDDEV(ppda),                         3)             AS stddev_ppda

FROM {{ ref('int_team_match_aggregates') }}
WHERE season = '{{ var("target_season", "2023") }}'
GROUP BY league, season, match_result, is_home
ORDER BY league, season, match_result, is_home
