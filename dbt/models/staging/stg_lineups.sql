-- =============================================================================
-- stg_lineups
-- =============================================================================
-- Source: raw.espn_lineups
--
-- One row per player per match appearance per league per season.
-- Casts all columns to correct types, COALESCEs all nullable integers to 0.
--
-- NOTE on saves column (from CLAUDE.md data rules):
--   89-90% NULL rate is expected and correct. saves is only populated for
--   goalkeepers (~1 in 11 players). COALESCE(saves, 0) is applied here.
--   Do not flag this as a data quality issue.
--
-- NOTE on sub_in / sub_out:
--   Values represent the minute of substitution (nullable integer).
--   Non-numeric source values (e.g. 'start') were coerced to NULL in the
--   ESPN scraper before loading to GCS. COALESCE to 0 here means "not
--   substituted" — use sub_in > 0 to identify actual substitution events.
--
-- DEVELOPMENT: LIMIT 1000 is active. Remove for production runs.
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    -- Identity
    CAST(player_name       AS STRING)    AS player_name,
    CAST(team              AS STRING)    AS team,
    CAST(league            AS STRING)    AS league,
    CAST(season            AS STRING)    AS season,

    -- Match context
    CAST(is_home           AS BOOLEAN)   AS is_home,
    CAST(position          AS STRING)    AS position,
    COALESCE(CAST(formation_place AS INT64), 0)  AS formation_place,

    -- Substitution info (minute, 0 = not substituted)
    COALESCE(CAST(sub_in   AS INT64), 0)         AS sub_in,
    COALESCE(CAST(sub_out  AS INT64), 0)         AS sub_out,

    -- Shot metrics
    COALESCE(CAST(shots_on_target  AS INT64), 0) AS shots_on_target,
    COALESCE(CAST(shots_faced      AS INT64), 0) AS shots_faced,

    -- Discipline
    COALESCE(CAST(fouls_committed  AS INT64), 0) AS fouls_committed,
    COALESCE(CAST(fouls_suffered   AS INT64), 0) AS fouls_suffered,
    COALESCE(CAST(offsides         AS INT64), 0) AS offsides,

    -- Goalkeeper stats (89-90% NULL — expected, goalkeepers only)
    COALESCE(CAST(saves            AS INT64), 0) AS saves,
    COALESCE(CAST(goals_conceded   AS INT64), 0) AS goals_conceded,

    -- Bonus columns (from CLAUDE.md)
    COALESCE(CAST(goal_assists     AS INT64), 0) AS goal_assists

FROM {{ source('raw', 'espn_lineups') }}
WHERE season = '{{ var("target_season", "2023") }}'
LIMIT 1000
