-- =============================================================================
-- stg_matches
-- =============================================================================
-- Source: raw.understat_matches
--
-- One row per match, per league, per season.
-- Casts all columns to correct types, adds derived columns:
--   result    — 'home_win', 'away_win', 'draw'
--   xg_diff   — home_xg - away_xg
--   score_diff — home_score - away_score
--
-- StatsBomb join: deferred until statsbomb_match_summary is loaded into raw.
-- When ready, LEFT JOIN on match_date + home_team + away_team (normalised).
--
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    -- Identity
    CAST(date AS DATE)                                AS match_date,
    CAST(home_team  AS STRING)                        AS home_team,
    CAST(away_team  AS STRING)                        AS away_team,
    CAST(league     AS STRING)                        AS league,
    CAST(season     AS STRING)                        AS season,

    -- Scores
    CAST(home_score AS INT64)                         AS home_score,
    CAST(away_score AS INT64)                         AS away_score,

    -- xG metrics
    CAST(home_xg    AS FLOAT64)                       AS home_xg,
    CAST(away_xg    AS FLOAT64)                       AS away_xg,
    CAST(home_np_xg AS FLOAT64)                       AS home_np_xg,
    CAST(away_np_xg AS FLOAT64)                       AS away_np_xg,

    -- PPDA (passes allowed per defensive action)
    CAST(home_ppda  AS FLOAT64)                       AS home_ppda,
    CAST(away_ppda  AS FLOAT64)                       AS away_ppda,

    -- Deep completions
    CAST(home_deep_completions AS INT64)              AS home_deep_completions,
    CAST(away_deep_completions AS INT64)              AS away_deep_completions,

    -- Derived columns
    CASE
        WHEN CAST(home_score AS INT64) > CAST(away_score AS INT64) THEN 'home_win'
        WHEN CAST(home_score AS INT64) < CAST(away_score AS INT64) THEN 'away_win'
        ELSE 'draw'
    END                                               AS result,

    CAST(home_xg    AS FLOAT64) - CAST(away_xg    AS FLOAT64) AS xg_diff,
    CAST(home_score AS INT64)   - CAST(away_score AS INT64)   AS score_diff

FROM {{ source('raw', 'understat_matches') }}
WHERE season = '{{ var("target_season", "2023") }}'
