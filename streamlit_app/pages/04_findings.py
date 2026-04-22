import sys
import os
import importlib.util
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

_bq_path = os.path.join(os.path.dirname(__file__), "..", "data", "bq_client.py")
_bq_spec = importlib.util.spec_from_file_location("bq_client", _bq_path)
_bq_mod = importlib.util.module_from_spec(_bq_spec)
_bq_spec.loader.exec_module(_bq_mod)
run_query = _bq_mod.run_query

from pipeline.config import GCP_PROJECT_ID

_DATASET = f"`{GCP_PROJECT_ID}.marts`"

_LEAGUE_COLORS = {
    "la_liga":        "#e74c3c",
    "premier_league": "#3498db",
    "bundesliga":     "#f39c12",
    "serie_a":        "#2ecc71",
    "ligue_1":        "#9b59b6",
}

_LEAGUE_LABELS = {
    "la_liga":        "La Liga",
    "premier_league": "Premier League",
    "bundesliga":     "Bundesliga",
    "serie_a":        "Serie A",
    "ligue_1":        "Ligue 1",
}


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

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


def _goals_xg_diff_by_league() -> pd.DataFrame:
    sql = f"""
    SELECT
        league,
        match_result,
        ROUND(AVG(avg_goals_scored - avg_xg_for), 4) AS goals_xg_diff
    FROM {_DATASET}.mart_winning_profiles
    WHERE season = '2023'
    GROUP BY league, match_result
    ORDER BY league, match_result
    """
    return run_query(sql)


def _goal_concentration() -> pd.DataFrame:
    # top_scorer_share and win_rate per team-season
    sql = f"""
    WITH player_goals AS (
        SELECT
            team,
            league,
            season,
            SUM(total_goals)  AS team_total_goals,
            MAX(total_goals)  AS top_scorer_goals
        FROM {_DATASET}.mart_player_performance
        WHERE season = '2023'
        GROUP BY team, league, season
    ),
    standings AS (
        SELECT
            team,
            league,
            season,
            win_rate,
            goals_for
        FROM {_DATASET}.mart_league_standings
        WHERE season = '2023'
    )
    SELECT
        p.team,
        p.league,
        p.season,
        SAFE_DIVIDE(p.top_scorer_goals, p.team_total_goals) AS top_scorer_share,
        s.win_rate,
        p.team_total_goals
    FROM player_goals p
    JOIN standings s
      ON p.team    = s.team
     AND p.league  = s.league
     AND p.season  = s.season
    WHERE p.team_total_goals > 0
    ORDER BY p.league, p.team
    """
    return run_query(sql)


def _winning_radar() -> pd.DataFrame:
    sql = f"""
    SELECT
        league,
        AVG(avg_xg_for)                                        AS avg_xg_for,
        SAFE_DIVIDE(AVG(avg_goals_scored), AVG(avg_xg_for))    AS finishing_efficiency,
        AVG(avg_ppda)                                          AS avg_ppda,
        AVG(avg_deep_completions)                              AS avg_deep_completions,
        AVG(avg_xg_against)                                    AS avg_xg_against
    FROM {_DATASET}.mart_winning_profiles
    WHERE season = '2023'
      AND match_result = 'win'
    GROUP BY league
    ORDER BY league
    """
    return run_query(sql)


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def _render_goals_xg_diff(df: pd.DataFrame):
    leagues = sorted(df["league"].unique())
    selected = st.multiselect(
        "Filter leagues",
        options=leagues,
        default=leagues,
        format_func=lambda x: _LEAGUE_LABELS.get(x, x),
        key="gxd_leagues",
    )
    if not selected:
        st.warning("Select at least one league.")
        return

    df = df[df["league"].isin(selected)].copy()
    result_colors = {"win": "#2ecc71", "draw": "#f39c12", "loss": "#e74c3c"}
    result_order  = {"win": 0, "draw": 1, "loss": 2}
    df["_sort"] = df["match_result"].map(result_order)
    df = df.sort_values(["league", "_sort"])

    fig = go.Figure()
    for result in ["win", "draw", "loss"]:
        sub = df[df["match_result"] == result]
        fig.add_trace(go.Bar(
            name=result.capitalize(),
            y=[_LEAGUE_LABELS.get(l, l) for l in sub["league"]],
            x=sub["goals_xg_diff"],
            orientation="h",
            marker_color=result_colors[result],
            hovertemplate="%{y}<br>Goals − xG: %{x:.3f}<extra>%{fullData.name}</extra>",
        ))

    fig.update_layout(
        barmode="group",
        xaxis=dict(title="Goals − xG (avg per match)", range=[-0.6, 0.6], zeroline=True, zerolinewidth=2),
        yaxis=dict(title=""),
        legend_title="Result",
        height=380,
        margin=dict(l=10, r=10, t=30, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.info(
        "Winning teams consistently **outperform their xG** — they score more goals than "
        "their chance quality predicts. Losing teams do the opposite: they generate chances "
        "but underconvert. This finishing differential compounds the underlying xG gap."
    )


def _render_goal_concentration(df: pd.DataFrame):
    df = df.copy()
    df["league_label"] = df["league"].map(lambda x: _LEAGUE_LABELS.get(x, x))
    df["top_scorer_pct"] = (df["top_scorer_share"] * 100).round(1)
    df["win_rate_pct"]   = (df["win_rate"] * 100).round(1)

    fig = px.scatter(
        df,
        x="top_scorer_pct",
        y="win_rate_pct",
        size="team_total_goals",
        color="league_label",
        color_discrete_map={_LEAGUE_LABELS.get(k, k): v for k, v in _LEAGUE_COLORS.items()},
        hover_name="team",
        hover_data={
            "top_scorer_pct": ":.1f",
            "win_rate_pct":   ":.1f",
            "league_label":   True,
            "team_total_goals": False,
        },
        labels={
            "top_scorer_pct": "Top scorer's share of team goals (%)",
            "win_rate_pct":   "Season win rate (%)",
            "league_label":   "League",
        },
        size_max=30,
    )
    fig.update_layout(height=450, margin=dict(l=10, r=10, t=30, b=40))
    st.plotly_chart(fig, use_container_width=True)
    st.info(
        "Goal concentration (how much one player dominates team scoring) shows **no clear "
        "relationship with win rate**. Teams with a dominant striker and teams with "
        "distributed goals win at similar rates — total xG quality is the stronger driver."
    )


def _minmax_norm(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    return (series - mn) / (mx - mn) * 100


def _render_radar(df: pd.DataFrame):
    df = df.copy()

    # Normalise dimensions (higher = better for all after inversion)
    df["xg_created"]         = _minmax_norm(df["avg_xg_for"])
    df["finishing_eff"]       = _minmax_norm(df["finishing_efficiency"])
    df["pressing"]            = _minmax_norm(1 / df["avg_ppda"].replace(0, float("nan")))
    df["territorial_control"] = _minmax_norm(df["avg_deep_completions"])
    df["defensive_solidity"]  = _minmax_norm(-df["avg_xg_against"])  # lower xG against = better

    dimensions = [
        "xg_created",
        "finishing_eff",
        "pressing",
        "territorial_control",
        "defensive_solidity",
    ]
    dim_labels = [
        "xG Created",
        "Finishing Efficiency",
        "Pressing Intensity",
        "Territorial Control",
        "Defensive Solidity",
    ]

    all_leagues = sorted(df["league"].unique())
    selected = st.multiselect(
        "Select leagues to display",
        options=all_leagues,
        default=all_leagues,
        format_func=lambda x: _LEAGUE_LABELS.get(x, x),
        key="radar_leagues",
    )
    if not selected:
        st.warning("Select at least one league.")
        return

    fig = go.Figure()
    for _, row in df[df["league"].isin(selected)].iterrows():
        vals = [row[d] for d in dimensions]
        vals_closed = vals + [vals[0]]
        labels_closed = dim_labels + [dim_labels[0]]
        color = _LEAGUE_COLORS.get(row["league"], "#888888")
        fig.add_trace(go.Scatterpolar(
            r=vals_closed,
            theta=labels_closed,
            fill="toself",
            name=_LEAGUE_LABELS.get(row["league"], row["league"]),
            line=dict(color=color),
            fillcolor=color,
            opacity=0.25,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        height=500,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.info(
        "**EPL and Bundesliga** winning profiles are defined by pressing intensity and xG "
        "creation. **Serie A** winners lean more on defensive solidity — lower xG conceded "
        "is their differentiator. **xG creation + finishing efficiency** is the universal "
        "constant across all five leagues."
    )


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Advanced Insights
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Advanced Insights: Finishing, Concentration & Profiles")

    # --- 1. Goals vs xG differential ---
    st.markdown("#### Goals vs xG Differential by Result")
    with st.spinner("Loading finishing data…"):
        try:
            gxd = _goals_xg_diff_by_league()
        except Exception as e:
            st.error(f"Failed to load goals/xG differential: {e}")
            gxd = None

    if gxd is not None and not gxd.empty:
        _render_goals_xg_diff(gxd)
    elif gxd is not None:
        st.error("Goals/xG differential query returned no rows for season 2023.")

    # --- 2. Goal concentration scatter ---
    st.markdown("#### Goal Concentration vs Win Rate")
    with st.spinner("Loading concentration data…"):
        try:
            conc = _goal_concentration()
        except Exception as e:
            st.error(f"Failed to load goal concentration data: {e}")
            conc = None

    if conc is not None and not conc.empty:
        _render_goal_concentration(conc)
    elif conc is not None:
        st.error("Goal concentration query returned no rows for season 2023.")

    # --- 3. Radar chart ---
    st.markdown("#### Winning Profile Radar Chart (per League)")
    with st.spinner("Loading radar data…"):
        try:
            radar = _winning_radar()
        except Exception as e:
            st.error(f"Failed to load radar data: {e}")
            radar = None

    if radar is not None and not radar.empty:
        _render_radar(radar)
    elif radar is not None:
        st.error("Radar query returned no rows for winning teams in season 2023.")
