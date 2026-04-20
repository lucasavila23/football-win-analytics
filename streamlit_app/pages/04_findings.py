import sys
import os
import importlib.util
import streamlit as st
import pandas as pd

_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

_bq_path = os.path.join(os.path.dirname(__file__), "..", "data", "bq_client.py")
_bq_spec = importlib.util.spec_from_file_location("bq_client", _bq_path)
_bq_mod = importlib.util.module_from_spec(_bq_spec)
_bq_spec.loader.exec_module(_bq_mod)
run_query = _bq_mod.run_query

from pipeline.config import GCP_PROJECT_ID

_DATASET = f"`{GCP_PROJECT_ID}.marts`"


def _winning_profiles() -> pd.DataFrame:
    sql = f"""
    SELECT
        match_result,
        avg_xg_for,
        avg_xg_against,
        avg_ppda,
        avg_deep_completions
    FROM {_DATASET}.mart_winning_profiles
    WHERE season = '2023'
    ORDER BY match_result
    """
    return run_query(sql)


def _league_standings() -> pd.DataFrame:
    sql = f"""
    SELECT
        team,
        wins,
        draws,
        losses,
        goals_for,
        goals_against,
        total_xg_for,
        avg_ppda,
        points
    FROM {_DATASET}.mart_league_standings
    WHERE season = '2023'
      AND league = 'la_liga'
    ORDER BY points DESC, goals_for DESC
    LIMIT 20
    """
    return run_query(sql)


def _top_players() -> pd.DataFrame:
    sql = f"""
    SELECT
        player_name,
        team,
        league,
        total_xg,
        total_goals,
        xg_per_90,
        match_appearances
    FROM {_DATASET}.mart_player_performance
    WHERE season = '2023'
    ORDER BY total_xg DESC
    LIMIT 10
    """
    return run_query(sql)


def render():
    st.title("Key Findings")

    with st.spinner("Loading data from BigQuery…"):
        try:
            wp = _winning_profiles()
        except Exception as e:
            st.error(f"Failed to load winning profiles: {e}")
            wp = None

    if wp is not None and not wp.empty:
        result_order = {"win": 0, "draw": 1, "loss": 2}
        wp["_sort"] = wp["match_result"].map(result_order)
        wp = wp.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)

        # --- xG signal ---
        st.markdown("### xG Signal: Wins vs Draws vs Losses")
        xg_chart = wp.set_index("match_result")[["avg_xg_for", "avg_xg_against"]]
        st.bar_chart(xg_chart)
        if "win" in wp["match_result"].values and "loss" in wp["match_result"].values:
            win_xg = wp.loc[wp["match_result"] == "win", "avg_xg_for"].iloc[0]
            loss_xg = wp.loc[wp["match_result"] == "loss", "avg_xg_for"].iloc[0]
            pct_diff = ((win_xg - loss_xg) / loss_xg * 100) if loss_xg else 0
            st.markdown(
                f"Winning teams generate **{win_xg:.3f} avg xG for** vs **{loss_xg:.3f}** "
                f"for losing teams — a **{pct_diff:.0f}% difference**. xG is the strongest "
                "single predictor of match result in this dataset."
            )

        # --- PPDA ---
        st.markdown("### Pressing Intensity (PPDA)")
        ppda_chart = wp.set_index("match_result")[["avg_ppda"]]
        st.bar_chart(ppda_chart)
        st.markdown(
            "Winning teams show lower PPDA (fewer passes allowed per defensive action = "
            "more intense press), but the gap between wins and losses is modest. Pressing "
            "intensity is a contributing factor — xG creation is the stronger signal."
        )

        # --- Deep completions ---
        st.markdown("### Dangerous Area Penetration (Deep Completions)")
        dc_chart = wp.set_index("match_result")[["avg_deep_completions"]]
        st.bar_chart(dc_chart)
        st.markdown(
            "Winning teams complete more passes into the danger zone. Deep completions "
            "correlate with xG — teams that penetrate deeper create higher-quality chances."
        )
    else:
        if wp is not None:
            st.error("Winning profiles query returned no rows for season 2023.")

    st.markdown("---")

    # --- League standings ---
    st.markdown("### La Liga 2023 — League Standings")
    with st.spinner("Loading standings…"):
        try:
            standings = _league_standings()
        except Exception as e:
            st.error(f"Failed to load standings: {e}")
            standings = None

    if standings is not None and not standings.empty:
        st.dataframe(
            standings,
            column_config={
                "team": st.column_config.TextColumn("Team"),
                "wins": st.column_config.NumberColumn("W", format="%d"),
                "draws": st.column_config.NumberColumn("D", format="%d"),
                "losses": st.column_config.NumberColumn("L", format="%d"),
                "goals_for": st.column_config.NumberColumn("GF", format="%d"),
                "goals_against": st.column_config.NumberColumn("GA", format="%d"),
                "total_xg_for": st.column_config.NumberColumn("Total xG For", format="%.2f"),
                "avg_ppda": st.column_config.NumberColumn("Avg PPDA", format="%.3f"),
                "points": st.column_config.NumberColumn("Pts", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.markdown(
            "Top teams by points tend to also lead on total xG — confirming that "
            "chance quality, not just finishing luck, drives league position over a season."
        )
    elif standings is not None:
        st.error("Standings query returned no rows for La Liga 2023.")

    st.markdown("---")

    # --- Top players by xG ---
    st.markdown("### Top 10 Players by xG — Season 2023 (All Leagues)")
    with st.spinner("Loading player data…"):
        try:
            players = _top_players()
        except Exception as e:
            st.error(f"Failed to load player performance: {e}")
            players = None

    if players is not None and not players.empty:
        st.dataframe(
            players,
            column_config={
                "player_name": st.column_config.TextColumn("Player"),
                "team": st.column_config.TextColumn("Team"),
                "league": st.column_config.TextColumn("League"),
                "total_xg": st.column_config.NumberColumn("Total xG", format="%.3f"),
                "total_goals": st.column_config.NumberColumn("Goals", format="%d"),
                "xg_per_90": st.column_config.NumberColumn("xG/90", format="%.3f"),
                "match_appearances": st.column_config.NumberColumn("Apps", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.markdown(
            "xG/90 adjusts for playing time — the players who consistently create "
            "high-quality chances per 90 minutes are the ones driving their teams' "
            "winning profiles above."
        )
    elif players is not None:
        st.error("Player performance query returned no rows for season 2023.")

    st.caption(
        "Note: analysis above uses season = 2023 data only to minimise BigQuery bytes "
        "scanned. Full 10-season analysis (2014–2023) is available in "
        "`notebooks/analysis/winning_profiles_queries.py` and will be incorporated "
        "after the complete pipeline re-run with all season filters removed from dbt models."
    )
