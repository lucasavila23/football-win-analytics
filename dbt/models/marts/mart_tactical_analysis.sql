-- =============================================================================
-- mart_tactical_analysis
-- =============================================================================
-- Team-level tactical metrics aggregated over a full season.
-- Focuses on pressing intensity (PPDA) and territory penetration
-- (deep completions) — the two metrics most predictive of winning style.
--
-- One row per team per league per season.
--
-- PPDA interpretation: lower = more aggressive press.
--   Elite presser: < 8.0
--   Average:       8.0 – 12.0
--   Low-press:     > 12.0
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    team,
    league,
    season,

    COUNT(*)                                                AS matches_played,

    -- Pressing metrics
    ROUND(AVG(ppda),                   3)                  AS avg_ppda,
    ROUND(MIN(ppda),                   3)                  AS best_ppda,
    ROUND(MAX(ppda),                   3)                  AS worst_ppda,
    ROUND(STDDEV(ppda),                3)                  AS ppda_consistency,

    -- Opponent pressing
    ROUND(AVG(opponent_ppda),          3)                  AS avg_opponent_ppda,

    -- Territory / carry
    ROUND(AVG(deep_completions),       1)                  AS avg_deep_completions,
    ROUND(SUM(deep_completions),       0)                  AS total_deep_completions,

    -- xG context
    ROUND(AVG(xg_for),                 3)                  AS avg_xg_for,
    ROUND(AVG(np_xg_for),              3)                  AS avg_np_xg_for,

    -- Win context for interpretation
    SUM(CASE WHEN match_result = 'win' THEN 1 ELSE 0 END)  AS wins,
    ROUND(
        {{ calculate_win_rate(
            'SUM(CASE WHEN match_result = \'win\' THEN 1 ELSE 0 END)',
            'COUNT(*)'
        ) }},
        3
    )                                                      AS win_rate

FROM {{ ref('int_team_match_aggregates') }}
WHERE season = '{{ var("target_season", "2023") }}'
GROUP BY team, league, season
ORDER BY league, season, avg_ppda ASC
