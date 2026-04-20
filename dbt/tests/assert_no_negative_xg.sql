-- =============================================================================
-- assert_no_negative_xg
-- =============================================================================
-- Singular test: returns rows where xG is negative.
-- An empty result = test passes. Any rows returned = test fails.
--
-- xG (expected goals) cannot be negative by definition. A negative value
-- would indicate a data corruption in the Understat scraper or raw load.
-- =============================================================================

SELECT
    match_date,
    home_team,
    away_team,
    home_xg,
    away_xg,
    league,
    season

FROM {{ ref('stg_matches') }}

WHERE home_xg < 0
   OR away_xg < 0
