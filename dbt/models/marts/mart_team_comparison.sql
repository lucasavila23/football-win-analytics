-- =============================================================================
-- mart_team_comparison
-- =============================================================================
-- Cross-team comparison table with all key metrics for a season,
-- plus league-relative z-scores so the frontend can show "above average".
--
-- One row per team per league per season.
-- Designed for the Supabase comparison view (Lovable frontend).
-- =============================================================================

{{ config(materialized='table') }}

WITH team_season AS (
    SELECT
        team,
        league,
        season,
        COUNT(*)                                                    AS matches_played,
        SUM(CASE WHEN match_result = 'win'  THEN 1 ELSE 0 END)     AS wins,
        SUM(CASE WHEN match_result = 'draw' THEN 1 ELSE 0 END)     AS draws,
        SUM(CASE WHEN match_result = 'loss' THEN 1 ELSE 0 END)     AS losses,
        SUM(points)                                                 AS points,
        SUM(goals_scored)                                           AS goals_for,
        SUM(goals_conceded)                                         AS goals_against,
        ROUND(SUM(xg_for),      2)                                  AS total_xg_for,
        ROUND(SUM(xg_against),  2)                                  AS total_xg_against,
        ROUND(AVG(xg_for),      3)                                  AS avg_xg_for,
        ROUND(AVG(xg_against),  3)                                  AS avg_xg_against,
        ROUND(AVG(ppda),        3)                                  AS avg_ppda,
        ROUND(AVG(deep_completions), 1)                             AS avg_deep_completions
    FROM {{ ref('int_team_match_aggregates') }}
    WHERE season = '{{ var("target_season", "2023") }}'
    GROUP BY team, league, season
),

league_stats AS (
    SELECT
        league,
        season,
        AVG(avg_xg_for)          AS league_avg_xg_for,
        STDDEV(avg_xg_for)       AS league_std_xg_for,
        AVG(avg_ppda)            AS league_avg_ppda,
        STDDEV(avg_ppda)         AS league_std_ppda,
        AVG(avg_deep_completions) AS league_avg_deep,
        STDDEV(avg_deep_completions) AS league_std_deep
    FROM team_season
    GROUP BY league, season
)

SELECT
    ts.team,
    ts.league,
    ts.season,
    ts.matches_played,
    ts.wins,
    ts.draws,
    ts.losses,
    ts.points,
    ts.goals_for,
    ts.goals_against,
    ts.goals_for - ts.goals_against                                 AS goal_difference,
    ts.total_xg_for,
    ts.total_xg_against,
    ts.avg_xg_for,
    ts.avg_xg_against,
    ts.avg_ppda,
    ts.avg_deep_completions,
    ROUND(
        {{ calculate_win_rate('ts.wins', 'ts.matches_played') }},
        3
    )                                                               AS win_rate,

    -- League-relative z-scores (positive = above average)
    ROUND(SAFE_DIVIDE(ts.avg_xg_for - ls.league_avg_xg_for,  ls.league_std_xg_for), 2)
                                                                    AS xg_for_z,
    -- PPDA z-score is inverted (lower PPDA = better = positive z)
    ROUND(SAFE_DIVIDE(ls.league_avg_ppda - ts.avg_ppda, ls.league_std_ppda), 2)
                                                                    AS ppda_z,
    ROUND(SAFE_DIVIDE(ts.avg_deep_completions - ls.league_avg_deep, ls.league_std_deep), 2)
                                                                    AS deep_completions_z

FROM team_season ts
JOIN league_stats ls
    ON ts.league = ls.league
   AND ts.season = ls.season
ORDER BY ts.league, ts.season, ts.points DESC
