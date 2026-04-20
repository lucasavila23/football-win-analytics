-- =============================================================================
-- int_head_to_head
-- =============================================================================
-- Historical head-to-head record between every pair of teams.
-- One row per (team, opponent, league, season) pair — not per match.
--
-- The "canonical" team pair uses alphabetical ordering of team names to avoid
-- double-counting (team_a < team_b always).
--
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    CASE WHEN team < opponent THEN team     ELSE opponent END   AS team_a,
    CASE WHEN team < opponent THEN opponent ELSE team     END   AS team_b,
    league,
    season,

    COUNT(*)                                                    AS matches_played,

    SUM(CASE
        WHEN team < opponent AND match_result = 'win'  THEN 1
        WHEN team > opponent AND match_result = 'loss' THEN 1
        ELSE 0
    END)                                                        AS team_a_wins,

    SUM(CASE WHEN match_result = 'draw' THEN 1 ELSE 0 END)      AS draws,

    SUM(CASE
        WHEN team < opponent AND match_result = 'loss' THEN 1
        WHEN team > opponent AND match_result = 'win'  THEN 1
        ELSE 0
    END)                                                        AS team_b_wins,

    SUM(CASE WHEN team < opponent THEN goals_scored  ELSE goals_conceded END) AS team_a_goals,
    SUM(CASE WHEN team < opponent THEN goals_conceded ELSE goals_scored  END) AS team_b_goals,

    ROUND(AVG(CASE WHEN team < opponent THEN xg_for  ELSE xg_against END), 3) AS team_a_avg_xg,
    ROUND(AVG(CASE WHEN team < opponent THEN xg_against ELSE xg_for  END), 3) AS team_b_avg_xg

FROM {{ ref('int_team_match_aggregates') }}
GROUP BY
    CASE WHEN team < opponent THEN team     ELSE opponent END,
    CASE WHEN team < opponent THEN opponent ELSE team     END,
    league,
    season

