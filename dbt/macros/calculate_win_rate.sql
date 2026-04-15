-- =============================================================================
-- calculate_win_rate(wins_col, matches_col)
-- =============================================================================
-- Returns wins / matches_played as a ratio, safe against division by zero.
-- Uses SAFE_DIVIDE which returns NULL (not an error) when denominator = 0.
--
-- Usage:
--   {{ calculate_win_rate('wins', 'matches_played') }}
--   → SAFE_DIVIDE(wins, matches_played)
-- =============================================================================

{% macro calculate_win_rate(wins_col, matches_col) %}
    SAFE_DIVIDE({{ wins_col }}, {{ matches_col }})
{% endmacro %}
