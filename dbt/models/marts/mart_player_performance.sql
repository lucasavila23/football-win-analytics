-- =============================================================================
-- mart_player_performance
-- =============================================================================
-- Season-aggregated player statistics — one row per player per team per
-- league per season.
--
-- Sources: stg_player_stats (Understat xG metrics)
--
-- NOTE: stg_player_stats does not carry a match date, so per-match breakdown
-- is not available here. Aggregation is at season level.
--
-- GROUP-BY RULE (immutable, from CLAUDE.md):
--   Always group by player_name + team + league + season.
--   player_name alone would merge stats across transfers and multi-league apps.
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    player_name,
    team,
    league,
    season,

    -- Appearances proxy (sum of match appearances)
    COUNT(*)                                        AS match_appearances,

    SUM(minutes)                                    AS total_minutes,
    SUM(goals)                                      AS total_goals,
    SUM(assists)                                    AS total_assists,
    SUM(own_goals)                                  AS total_own_goals,
    SUM(shots)                                      AS total_shots,

    -- xG metrics
    ROUND(SUM(xg),          3)                      AS total_xg,
    ROUND(SUM(xa),          3)                      AS total_xa,
    ROUND(SUM(xg_chain),    3)                      AS total_xg_chain,
    ROUND(SUM(xg_buildup),  3)                      AS total_xg_buildup,

    -- Per-90 (guarded against 0 minutes)
    ROUND(SAFE_DIVIDE(SUM(xg),    SUM(minutes)) * 90, 3) AS xg_per_90,
    ROUND(SAFE_DIVIDE(SUM(goals), SUM(minutes)) * 90, 3) AS goals_per_90,

    -- Discipline
    SUM(key_passes)                                 AS total_key_passes,
    SUM(yellow_card)                                AS total_yellow_cards,
    SUM(red_card)                                   AS total_red_cards,

    -- Position (most frequent position across appearances)
    APPROX_TOP_COUNT(position, 1)[OFFSET(0)].value  AS primary_position

FROM {{ ref('stg_player_stats') }}
GROUP BY player_name, team, league, season
ORDER BY league, season, total_xg DESC
