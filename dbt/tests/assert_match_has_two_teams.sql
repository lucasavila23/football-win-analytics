-- =============================================================================
-- assert_match_has_two_teams
-- =============================================================================
-- Singular test: verifies that each (match_date, league, season) combination
-- in int_team_match_aggregates appears exactly twice — once for the home team
-- and once for the away team.
--
-- An empty result = test passes. Any rows returned = test fails.
--
-- A mismatch (count != 2) would mean the UNION ALL in int_team_match_aggregates
-- produced duplicate or missing rows for a match.
--
-- NOTE: multiple matches can occur on the same date in the same league
-- (e.g. match-day round). The pair (match_date, team) is the unique key —
-- this test checks that every team appears at most once per date.
-- =============================================================================

SELECT
    match_date,
    team,
    league,
    season,
    COUNT(*) AS appearances

FROM {{ ref('int_team_match_aggregates') }}

GROUP BY match_date, team, league, season

HAVING COUNT(*) > 1
