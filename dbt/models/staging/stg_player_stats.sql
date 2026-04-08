-- =============================================================================
-- stg_player_stats
-- =============================================================================
-- Source: raw.understat_player_stats
--
-- One row per player per match appearance per league per season.
-- Casts all columns to correct types.
--
-- Join with ESPN lineups is deferred to intermediate (int_player_match_joined).
-- The raw player_stats table does not carry a match date column, so the join
-- cannot happen at staging — it requires match-level context.
--
-- GROUP-BY RULE (immutable, from CLAUDE.md):
--   Always aggregate on: player_name + team + league + season
--   Never on player_name alone — breaks on transfers and multi-league players.
--
-- DEVELOPMENT: LIMIT 1000 is active. Remove for production runs.
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    -- Identity
    CAST(player_name  AS STRING)    AS player_name,
    CAST(team         AS STRING)    AS team,
    CAST(league       AS STRING)    AS league,
    CAST(season       AS STRING)    AS season,

    -- Playing time
    CAST(minutes      AS INT64)     AS minutes,

    -- Goal contributions
    CAST(goals        AS INT64)     AS goals,
    CAST(assists      AS INT64)     AS assists,

    -- Shot metrics
    CAST(shots        AS INT64)     AS shots,

    -- xG metrics
    CAST(xg           AS FLOAT64)   AS xg,
    CAST(xa           AS FLOAT64)   AS xa,
    CAST(xg_chain     AS FLOAT64)   AS xg_chain,
    CAST(xg_buildup   AS FLOAT64)   AS xg_buildup,

    -- Discipline / passing
    CAST(key_passes   AS INT64)     AS key_passes,
    CAST(yellow_card  AS INT64)     AS yellow_card,
    CAST(red_card     AS INT64)     AS red_card,

    -- Bonus columns (from CLAUDE.md)
    COALESCE(CAST(own_goals   AS INT64), 0)  AS own_goals,
    CAST(position             AS STRING)     AS position,
    CAST(position_id          AS INT64)      AS position_id

FROM {{ source('raw', 'understat_player_stats') }}
WHERE season = '{{ var("target_season", "2023") }}'
LIMIT 1000
