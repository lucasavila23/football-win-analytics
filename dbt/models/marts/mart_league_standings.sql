-- =============================================================================
-- mart_league_standings
-- =============================================================================
-- Points table — one row per team per league per season.
-- Ordered by points DESC, goal difference DESC (standard tiebreaker).
--
-- Columns consumed by the Supabase / Lovable frontend:
--   team, league, season, matches_played, wins, draws, losses,
--   points, goals_for, goals_against, goal_difference,
--   total_xg_for, total_xg_against, avg_ppda, win_rate
-- =============================================================================

{{ config(materialized='table') }}

SELECT
    team,
    league,
    season,

    COUNT(*)                                                AS matches_played,

    SUM(CASE WHEN match_result = 'win'  THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN match_result = 'draw' THEN 1 ELSE 0 END) AS draws,
    SUM(CASE WHEN match_result = 'loss' THEN 1 ELSE 0 END) AS losses,

    SUM(points)                                            AS points,

    SUM(goals_scored)                                      AS goals_for,
    SUM(goals_conceded)                                    AS goals_against,
    SUM(goals_scored) - SUM(goals_conceded)                AS goal_difference,

    ROUND(SUM(xg_for),      2)                             AS total_xg_for,
    ROUND(SUM(xg_against),  2)                             AS total_xg_against,
    ROUND(SUM(xg_for) - SUM(xg_against), 2)               AS total_xg_difference,

    ROUND(AVG(ppda), 3)                                    AS avg_ppda,
    ROUND(AVG(deep_completions), 1)                        AS avg_deep_completions,

    ROUND(
        {{ calculate_win_rate(
            'SUM(CASE WHEN match_result = \'win\' THEN 1 ELSE 0 END)',
            'COUNT(*)'
        ) }},
        3
    )                                                      AS win_rate

FROM {{ ref('int_team_match_aggregates') }}
GROUP BY team, league, season
ORDER BY league, season, points DESC, goal_difference DESC
