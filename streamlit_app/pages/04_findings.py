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
_bq_mod  = importlib.util.module_from_spec(_bq_spec)
_bq_spec.loader.exec_module(_bq_mod)
run_query = _bq_mod.run_query

from pipeline.config import GCP_PROJECT_ID

_DATASET = f"`{GCP_PROJECT_ID}.marts`"

# ── Color / label constants ────────────────────────────────────────────────────
LEAGUE_COLORS = {
    "la_liga":        "#e63946",
    "premier_league": "#457b9d",
    "bundesliga":     "#f4a261",
    "serie_a":        "#2a9d8f",
    "ligue_1":        "#8338ec",
}
LEAGUE_LABELS = {
    "la_liga":        "La Liga",
    "premier_league": "Premier League",
    "bundesliga":     "Bundesliga",
    "serie_a":        "Serie A",
    "ligue_1":        "Ligue 1",
}
RESULT_COLORS = {
    "win":  "#2ecc71",
    "draw": "#f39c12",
    "loss": "#e74c3c",
}
ALL_LEAGUES = list(LEAGUE_COLORS.keys())
ALL_SEASONS = ["2014","2015","2016","2017","2018","2019","2020","2021","2022","2023"]


# ── Shared dark layout helper ──────────────────────────────────────────────────
def _dark(**kwargs) -> dict:
    base = dict(
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font_color="#e2e8f0",
    )
    base.update(kwargs)
    return base


# ── Normalisation helper ───────────────────────────────────────────────────────
def _minmax(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty or valid.max() == valid.min():
        return pd.Series([50.0] * len(series), index=series.index)
    return (series - valid.min()) / (valid.max() - valid.min()) * 100


# ── Query functions ────────────────────────────────────────────────────────────

def _winning_profiles(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT
        league,
        match_result,
        AVG(avg_xg_for)           AS avg_xg_for,
        AVG(avg_xg_against)       AS avg_xg_against,
        AVG(avg_goals_scored)     AS avg_goals_scored,
        AVG(avg_ppda)             AS avg_ppda,
        AVG(avg_deep_completions) AS avg_deep_completions,
        AVG(avg_np_xg_for)        AS avg_np_xg_for,
        COUNT(*)                  AS sample_size
    FROM {_DATASET}.mart_winning_profiles
    WHERE {season_sql} AND {league_sql}
    GROUP BY league, match_result
    ORDER BY league, match_result
    """
    return run_query(sql)


def _league_standings(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT
        team,
        league,
        ROUND(AVG(wins),          1) AS wins,
        ROUND(AVG(draws),         1) AS draws,
        ROUND(AVG(losses),        1) AS losses,
        ROUND(AVG(goals_for),     1) AS goals_for,
        ROUND(AVG(goals_against), 1) AS goals_against,
        ROUND(AVG(total_xg_for),  2) AS total_xg_for,
        ROUND(AVG(avg_ppda),      3) AS avg_ppda,
        ROUND(AVG(points),        1) AS points
    FROM {_DATASET}.mart_league_standings
    WHERE {season_sql} AND {league_sql}
    GROUP BY team, league
    ORDER BY AVG(points) DESC, AVG(goals_for) DESC
    LIMIT 30
    """
    return run_query(sql)


def _top_players(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT
        player_name,
        team,
        league,
        ROUND(SUM(total_xg), 3)                                              AS total_xg,
        SUM(total_goals)                                                      AS total_goals,
        ROUND(SAFE_DIVIDE(SUM(total_xg), SUM(total_minutes)) * 90, 3)        AS xg_per_90,
        SUM(match_appearances)                                                AS match_appearances
    FROM {_DATASET}.mart_player_performance
    WHERE {season_sql} AND {league_sql}
    GROUP BY player_name, team, league
    ORDER BY total_xg DESC
    LIMIT 10
    """
    return run_query(sql)


def _goal_concentration(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    WITH player_goals AS (
        SELECT
            team,
            league,
            season,
            SUM(total_goals) AS team_total_goals,
            MAX(total_goals) AS top_scorer_goals
        FROM {_DATASET}.mart_player_performance
        WHERE {season_sql} AND {league_sql}
        GROUP BY team, league, season
    ),
    standings AS (
        SELECT team, league, season, win_rate
        FROM {_DATASET}.mart_league_standings
        WHERE {season_sql} AND {league_sql}
    )
    SELECT
        p.team,
        p.league,
        p.season,
        SAFE_DIVIDE(p.top_scorer_goals, NULLIF(p.team_total_goals, 0)) AS top_scorer_share,
        s.win_rate,
        p.team_total_goals
    FROM player_goals p
    JOIN standings s
      ON p.team   = s.team
     AND p.league = s.league
     AND p.season = s.season
    WHERE p.team_total_goals > 0
    ORDER BY p.league, p.team
    """
    return run_query(sql)


def _winning_radar(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT
        league,
        AVG(avg_xg_for)                                                AS avg_xg_for,
        SAFE_DIVIDE(AVG(avg_goals_scored), NULLIF(AVG(avg_xg_for), 0)) AS finishing_efficiency,
        NULLIF(AVG(avg_ppda), 0)                                       AS avg_ppda,
        AVG(avg_deep_completions)                                      AS avg_deep_completions,
        NULLIF(AVG(avg_xg_against), 0)                                 AS avg_xg_against
    FROM {_DATASET}.mart_winning_profiles
    WHERE {season_sql} AND {league_sql} AND match_result = 'win'
    GROUP BY league
    ORDER BY league
    """
    return run_query(sql)


# ── render ─────────────────────────────────────────────────────────────────────

def render():
    st.title("Key Findings")

    # ── Global filter bar ──────────────────────────────────────────────────────
    col_l, col_s = st.columns([3, 2])
    with col_l:
        selected_leagues = st.multiselect(
            "Leagues",
            options=ALL_LEAGUES,
            default=ALL_LEAGUES,
            format_func=lambda x: LEAGUE_LABELS[x],
            key="findings_leagues",
        )
    with col_s:
        season_mode = st.radio(
            "Season",
            options=["Single season", "Last 5 seasons avg", "Custom range"],
            horizontal=True,
            key="findings_season_mode",
        )

    if season_mode == "Single season":
        selected_season   = st.select_slider(
            "Select season",
            options=ALL_SEASONS,
            value="2023",
            key="findings_single_season",
        )
        season_filter_sql = f"season = '{selected_season}'"
        season_label      = f"Season {selected_season}"
    elif season_mode == "Last 5 seasons avg":
        selected_season   = None
        season_filter_sql = "season IN ('2019','2020','2021','2022','2023')"
        season_label      = "5-season avg (2019–2023)"
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            s_from = st.selectbox("From", ALL_SEASONS, index=0, key="s_from")
        with col_b:
            s_to   = st.selectbox("To",   ALL_SEASONS, index=len(ALL_SEASONS) - 1, key="s_to")
        valid_range       = [s for s in ALL_SEASONS if s_from <= s <= s_to]
        season_filter_sql = f"season IN ({','.join(repr(s) for s in valid_range)})"
        season_label      = f"Avg {s_from}–{s_to}"
        selected_season   = None

    if not selected_leagues:
        st.warning("Select at least one league.")
        return

    league_filter_sql = f"league IN ({','.join(repr(l) for l in selected_leagues)})"

    # ── Load winning profiles once — used for Charts A-E and Advanced Chart 1 ─
    with st.spinner("Loading match data from BigQuery…"):
        try:
            wp = _winning_profiles(season_filter_sql, league_filter_sql)
        except Exception as e:
            st.error(f"Failed to load winning profiles: {e}")
            wp = None

    if wp is None or wp.empty:
        if wp is not None:
            st.error("Winning profiles query returned no rows for the selected filters.")
    else:
        # ── Chart A — xG Created ──────────────────────────────────────────────
        st.markdown("### xG Created by Result")
        fig = go.Figure()
        for result in ["win", "draw", "loss"]:
            sub = wp[wp["match_result"] == result]
            if sub.empty:
                continue
            fig.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["avg_xg_for"].round(3),
                marker_color=RESULT_COLORS[result],
                text=sub["avg_xg_for"].round(2),
                textposition="outside",
            ))
        fig.update_layout(**_dark(
            barmode="group",
            title=f"Avg xG Created per Match by Result — {season_label}",
            yaxis_title="Avg xG For",
            legend_title="Result",
            height=420,
        ))
        st.plotly_chart(fig, use_container_width=True)
        wins_wp  = wp[wp["match_result"] == "win"]
        losses_wp = wp[wp["match_result"] == "loss"]
        if not wins_wp.empty and not losses_wp.empty:
            avg_win_xg  = wins_wp["avg_xg_for"].mean()
            avg_loss_xg = losses_wp["avg_xg_for"].mean()
            pct = ((avg_win_xg - avg_loss_xg) / avg_loss_xg * 100) if avg_loss_xg else 0
            st.markdown(
                f"Across selected leagues, winning teams create **{avg_win_xg:.3f} avg xG** "
                f"vs **{avg_loss_xg:.3f}** for losing teams — a **{pct:.0f}% gap**. "
                "xG is the strongest single predictor of match result in this dataset."
            )

        # ── Chart B — xG Against ─────────────────────────────────────────────
        st.markdown("### xG Conceded by Result")
        fig = go.Figure()
        for result in ["win", "draw", "loss"]:
            sub = wp[wp["match_result"] == result]
            if sub.empty:
                continue
            fig.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["avg_xg_against"].round(3),
                marker_color=RESULT_COLORS[result],
                text=sub["avg_xg_against"].round(2),
                textposition="outside",
            ))
        fig.update_layout(**_dark(
            barmode="group",
            title=f"Avg xG Conceded per Match by Result — {season_label}",
            yaxis_title="Avg xG Against",
            legend_title="Result",
            height=420,
        ))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(
            "Winning teams also concede fewer expected goals. "
            "The combination of creating more and conceding less defines winning teams."
        )

        # ── Chart C — Finishing Efficiency ────────────────────────────────────
        st.markdown("### Finishing Efficiency (Goals ÷ xG)")
        wp_fe = wp.copy()
        wp_fe["finishing_eff"] = (
            wp_fe["avg_goals_scored"]
            / wp_fe["avg_xg_for"].replace(0, float("nan"))
        ).round(3)

        fig = go.Figure()
        annotations = []
        for result in ["win", "draw", "loss"]:
            sub = wp_fe[wp_fe["match_result"] == result]
            if sub.empty:
                continue
            fig.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["finishing_eff"],
                marker_color=RESULT_COLORS[result],
                text=sub["finishing_eff"].round(2),
                textposition="outside",
            ))
            if result == "win":
                for _, row in sub[sub["finishing_eff"] > 1.2].iterrows():
                    annotations.append(dict(
                        x=LEAGUE_LABELS.get(row["league"], row["league"]),
                        y=row["finishing_eff"] + 0.05,
                        text="★ Overperforming xG",
                        showarrow=False,
                        font=dict(color="#f1c40f", size=10),
                    ))

        fig.add_hline(
            y=1.0, line_dash="dot", line_color="#94a3b8",
            annotation_text="Goals = xG baseline",
            annotation_font_color="#94a3b8",
        )
        fig.update_layout(**_dark(
            barmode="group",
            title=f"Finishing Efficiency (Goals ÷ xG) by Result — {season_label}",
            yaxis_title="Goals / xG",
            legend_title="Result",
            height=420,
            annotations=annotations,
        ))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(
            "A ratio above 1.0 means a team scored more goals than chance quality predicted. "
            "Winning teams consistently finish above xG expectations; losing teams fall below."
        )

        # ── Chart D — PPDA ────────────────────────────────────────────────────
        st.markdown("### Pressing Intensity (PPDA)")
        fig = go.Figure()
        for result in ["win", "draw", "loss"]:
            sub = wp[wp["match_result"] == result]
            if sub.empty:
                continue
            fig.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["avg_ppda"].round(3),
                marker_color=RESULT_COLORS[result],
                text=sub["avg_ppda"].round(2),
                textposition="outside",
            ))
        fig.update_layout(**_dark(
            barmode="group",
            title=f"Avg PPDA per Match by Result — {season_label}",
            yaxis_title="Avg PPDA",
            legend_title="Result",
            height=420,
        ))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Lower PPDA = more intense press (fewer passes allowed per defensive action).")
        st.markdown(
            "Winning teams generally press harder, but the PPDA gap between wins and losses "
            "is modest relative to the xG gap. Pressing is a contributing factor — chance "
            "quality is the primary driver."
        )

        # ── Chart E — Deep Completions ────────────────────────────────────────
        st.markdown("### Territorial Penetration (Deep Completions)")
        fig = go.Figure()
        for result in ["win", "draw", "loss"]:
            sub = wp[wp["match_result"] == result]
            if sub.empty:
                continue
            fig.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["avg_deep_completions"].round(2),
                marker_color=RESULT_COLORS[result],
                text=sub["avg_deep_completions"].round(1),
                textposition="outside",
            ))
        fig.update_layout(**_dark(
            barmode="group",
            title=f"Avg Deep Completions per Match by Result — {season_label}",
            yaxis_title="Avg Deep Completions",
            legend_title="Result",
            height=420,
        ))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(
            "Deep completions (passes into the opponent's danger zone) track closely with "
            "xG — teams that penetrate deeper create higher-quality chances."
        )

    st.markdown("---")

    # ── League standings ───────────────────────────────────────────────────────
    st.markdown(f"### League Standings — {season_label}")
    with st.spinner("Loading standings…"):
        try:
            standings = _league_standings(season_filter_sql, league_filter_sql)
        except Exception as e:
            st.error(f"Failed to load standings: {e}")
            standings = None

    if standings is not None and not standings.empty:
        standings["league_label"] = standings["league"].map(
            lambda x: LEAGUE_LABELS.get(x, x)
        )
        display_cols = [
            "team", "league_label", "wins", "draws", "losses",
            "goals_for", "goals_against", "total_xg_for", "avg_ppda", "points",
        ]
        st.dataframe(
            standings[display_cols],
            column_config={
                "team":          st.column_config.TextColumn("Team"),
                "league_label":  st.column_config.TextColumn("League"),
                "wins":          st.column_config.NumberColumn("W",        format="%.1f"),
                "draws":         st.column_config.NumberColumn("D",        format="%.1f"),
                "losses":        st.column_config.NumberColumn("L",        format="%.1f"),
                "goals_for":     st.column_config.NumberColumn("GF",       format="%.1f"),
                "goals_against": st.column_config.NumberColumn("GA",       format="%.1f"),
                "total_xg_for":  st.column_config.NumberColumn("Total xG", format="%.2f"),
                "avg_ppda":      st.column_config.NumberColumn("Avg PPDA", format="%.3f"),
                "points":        st.column_config.NumberColumn("Pts",      format="%.1f"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.markdown(
            "Top teams by points tend to also lead on total xG — confirming that chance "
            "quality, not just finishing luck, drives league position over a season."
        )
    elif standings is not None:
        st.error("Standings query returned no rows for the selected filters.")

    st.markdown("---")

    # ── Top players ────────────────────────────────────────────────────────────
    st.markdown(f"### Top 10 Players by xG — {season_label}")
    with st.spinner("Loading player data…"):
        try:
            players = _top_players(season_filter_sql, league_filter_sql)
        except Exception as e:
            st.error(f"Failed to load player performance: {e}")
            players = None

    if players is not None and not players.empty:
        players["league_label"] = players["league"].map(
            lambda x: LEAGUE_LABELS.get(x, x)
        )
        display_cols = [
            "player_name", "team", "league_label",
            "total_xg", "total_goals", "xg_per_90", "match_appearances",
        ]
        st.dataframe(
            players[display_cols],
            column_config={
                "player_name":       st.column_config.TextColumn("Player"),
                "team":              st.column_config.TextColumn("Team"),
                "league_label":      st.column_config.TextColumn("League"),
                "total_xg":          st.column_config.NumberColumn("Total xG", format="%.3f"),
                "total_goals":       st.column_config.NumberColumn("Goals",     format="%d"),
                "xg_per_90":         st.column_config.NumberColumn("xG/90",     format="%.3f"),
                "match_appearances": st.column_config.NumberColumn("Apps",      format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.markdown(
            "xG/90 adjusts for playing time — the players consistently creating high-quality "
            "chances per 90 minutes are the ones driving their teams' winning profiles."
        )
    elif players is not None:
        st.error("Player performance query returned no rows for the selected filters.")

    st.caption(
        f"Showing: {season_label} · "
        f"Leagues: {', '.join(LEAGUE_LABELS.get(l, l) for l in selected_leagues)}"
    )

    # ── Advanced Insights ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Advanced Insights: Finishing, Concentration & Profiles")

    # ── Advanced Chart 1 — Goals vs xG Differential ───────────────────────────
    st.markdown("#### Goals vs xG Differential by Result")
    if wp is not None and not wp.empty:
        gxd = wp.copy()
        gxd["goals_xg_diff"] = (gxd["avg_goals_scored"] - gxd["avg_xg_for"]).round(4)

        fig = go.Figure()
        for result in ["win", "draw", "loss"]:
            sub = gxd[gxd["match_result"] == result]
            if sub.empty:
                continue
            fig.add_trace(go.Bar(
                name=result.capitalize(),
                y=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                x=sub["goals_xg_diff"],
                orientation="h",
                marker_color=RESULT_COLORS[result],
                hovertemplate="%{y}<br>Goals − xG: %{x:.3f}<extra>%{fullData.name}</extra>",
            ))
        fig.update_layout(**_dark(
            barmode="group",
            title=f"Goals − xG (Avg per Match) by Result — {season_label}",
            xaxis=dict(
                title="Goals − xG (avg per match)",
                range=[-0.6, 0.6],
                zeroline=True,
                zerolinewidth=2,
                zerolinecolor="#94a3b8",
            ),
            yaxis_title="",
            legend_title="Result",
            height=420,
        ))
        st.plotly_chart(fig, use_container_width=True)
        st.info(
            "Winning teams consistently **outperform their xG** — they score more goals than "
            "their chance quality predicts. Losing teams do the opposite: they generate chances "
            "but underconvert. This finishing differential compounds the underlying xG gap."
        )
    else:
        st.warning("No winning profiles data available for the selected filters.")

    # ── Advanced Chart 2 — Goal Concentration vs Win Rate ─────────────────────
    st.markdown("#### Goal Concentration vs Win Rate")
    with st.spinner("Loading concentration data…"):
        try:
            conc = _goal_concentration(season_filter_sql, league_filter_sql)
        except Exception as e:
            st.error(f"Failed to load goal concentration data: {e}")
            conc = None

    if conc is not None:
        if len(conc) < 3:
            st.warning(
                "Not enough data for the selected filters — try expanding the season "
                "range or selecting more leagues."
            )
        else:
            conc = conc.copy()
            conc["league_label"]   = conc["league"].map(lambda x: LEAGUE_LABELS.get(x, x))
            conc["top_scorer_pct"] = (conc["top_scorer_share"] * 100).round(1)
            conc["win_rate_pct"]   = (conc["win_rate"] * 100).round(1)
            conc["bubble_size"]    = conc["team_total_goals"].fillna(0)

            color_map = {LEAGUE_LABELS.get(k, k): v for k, v in LEAGUE_COLORS.items()}
            fig = px.scatter(
                conc,
                x="top_scorer_pct",
                y="win_rate_pct",
                size="bubble_size",
                color="league_label",
                color_discrete_map=color_map,
                hover_name="team",
                hover_data={
                    "top_scorer_pct": ":.1f",
                    "win_rate_pct":   ":.1f",
                    "league_label":   True,
                    "bubble_size":    False,
                    "season":         True,
                },
                labels={
                    "top_scorer_pct": "Top scorer's share of team goals (%)",
                    "win_rate_pct":   "Season win rate (%)",
                    "league_label":   "League",
                },
                title=f"Goal Concentration vs Win Rate — {season_label}",
                size_max=30,
            )
            fig.update_layout(**_dark(height=480))
            st.plotly_chart(fig, use_container_width=True)
            st.info(
                "Goal concentration (how much one player dominates team scoring) shows "
                "**no clear relationship with win rate**. Teams with a dominant striker "
                "and teams with distributed goals win at similar rates — total xG quality "
                "is the stronger driver."
            )

    # ── Advanced Chart 3 — Winning Profile Radar ─────────────────────────────
    st.markdown("#### Winning Profile Radar Chart (per League)")
    with st.spinner("Loading radar data…"):
        try:
            radar_raw = _winning_radar(season_filter_sql, league_filter_sql)
        except Exception as e:
            st.error(f"Failed to load radar data: {e}")
            radar_raw = None

    if radar_raw is not None and not radar_raw.empty:
        radar = radar_raw.copy()

        # Derived values — NaN/0 inputs produce NaN (missing data, not zero)
        radar["_xg_created"]  = radar["avg_xg_for"].where(
            radar["avg_xg_for"].notna() & (radar["avg_xg_for"] > 0)
        )
        radar["_finishing"]   = radar["finishing_efficiency"].where(
            radar["finishing_efficiency"].notna() & (radar["finishing_efficiency"] > 0)
        )
        radar["_pressing"]    = (1.0 / radar["avg_ppda"]).where(
            radar["avg_ppda"].notna() & (radar["avg_ppda"] > 0)
        )
        radar["_territorial"] = radar["avg_deep_completions"].where(
            radar["avg_deep_completions"].notna() & (radar["avg_deep_completions"] > 0)
        )
        radar["_defensive"]   = (1.0 / radar["avg_xg_against"]).where(
            radar["avg_xg_against"].notna() & (radar["avg_xg_against"] > 0)
        )

        # Data quality warnings — show before plotting so user knows why gaps appear
        _dim_raw_cols = {
            "xG Created":         "_xg_created",
            "Finishing Eff":      "_finishing",
            "Pressing Intensity": "_pressing",
            "Territorial":        "_territorial",
            "Defensive Solidity": "_defensive",
        }
        missing = []
        for _, row in radar.iterrows():
            label = LEAGUE_LABELS.get(row["league"], row["league"])
            for dim_name, col in _dim_raw_cols.items():
                if pd.isna(row[col]):
                    missing.append(f"**{label}** — {dim_name}")
        if missing:
            st.warning(
                "Missing or zero data excluded from radar:\n\n"
                + "\n".join(f"- {m}" for m in missing)
            )

        # Normalise 0-100 across leagues for each dimension
        norm_map = {c: c + "_norm" for c in _dim_raw_cols.values()}
        for raw_col, norm_col in norm_map.items():
            radar[norm_col] = _minmax(radar[raw_col])

        dim_labels_list = list(_dim_raw_cols.keys())
        norm_cols_list  = list(norm_map.values())

        all_radar_leagues = sorted(radar["league"].unique())
        radar_selected = st.multiselect(
            "Select leagues to display",
            options=all_radar_leagues,
            default=all_radar_leagues,
            format_func=lambda x: LEAGUE_LABELS.get(x, x),
            key="radar_leagues",
        )
        if not radar_selected:
            st.warning("Select at least one league.")
        else:
            fig = go.Figure()
            for _, row in radar[radar["league"].isin(radar_selected)].iterrows():
                vals = [row[c] for c in norm_cols_list]
                # None creates a gap in the trace for missing dimensions
                vals_closed   = [None if pd.isna(v) else v for v in vals] + [
                    None if pd.isna(vals[0]) else vals[0]
                ]
                labels_closed = dim_labels_list + [dim_labels_list[0]]
                color = LEAGUE_COLORS.get(row["league"], "#888888")
                fig.add_trace(go.Scatterpolar(
                    r=vals_closed,
                    theta=labels_closed,
                    fill="toself",
                    name=LEAGUE_LABELS.get(row["league"], row["league"]),
                    line=dict(color=color),
                    fillcolor=color,
                    opacity=0.3,
                ))
            fig.update_layout(**_dark(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 100]),
                    bgcolor="#0f172a",
                ),
                title=f"Winning Team Profiles by League — {season_label}",
                showlegend=True,
                height=520,
            ))
            st.plotly_chart(fig, use_container_width=True)
            st.info(
                "**EPL and Bundesliga** winning profiles are driven by pressing intensity "
                "and xG creation. **Serie A** winners lean on defensive solidity — lower "
                "xG conceded is their primary differentiator. **xG creation + finishing "
                "efficiency** is the universal constant across all five leagues."
            )
    elif radar_raw is not None:
        st.error("Radar query returned no rows for winning teams in the selected filters.")
