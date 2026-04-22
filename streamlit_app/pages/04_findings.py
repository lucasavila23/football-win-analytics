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

# ── Constants ──────────────────────────────────────────────────────────────────
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


# ── Layout helper ──────────────────────────────────────────────────────────────
def _base_layout(height: int = 420) -> dict:
    return dict(
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#111111", family="sans-serif"),
        height=height,
        margin=dict(t=20, b=40, l=60, r=20),
        xaxis=dict(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb"),
        yaxis=dict(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb"),
    )


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
        AVG(avg_goals_conceded)   AS avg_goals_conceded,
        AVG(avg_ppda)             AS avg_ppda,
        AVG(avg_opponent_ppda)    AS avg_opponent_ppda,
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
        AVG(wins)          AS wins,
        AVG(draws)         AS draws,
        AVG(losses)        AS losses,
        AVG(goals_for)     AS goals_for,
        AVG(goals_against) AS goals_against,
        AVG(total_xg_for)  AS total_xg_for,
        AVG(avg_ppda)      AS avg_ppda,
        AVG(points)        AS points
    FROM {_DATASET}.mart_league_standings
    WHERE {season_sql} AND {league_sql}
    GROUP BY team, league
    ORDER BY AVG(points) DESC, AVG(goals_for) DESC
    LIMIT 40
    """
    return run_query(sql)


def _top_players(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT
        player_name,
        team,
        league,
        season,
        SUM(total_xg)          AS total_xg,
        SUM(total_goals)       AS total_goals,
        AVG(xg_per_90)         AS xg_per_90,
        SUM(match_appearances) AS match_appearances
    FROM {_DATASET}.mart_player_performance
    WHERE {season_sql} AND {league_sql}
    GROUP BY player_name, team, league, season
    ORDER BY SUM(total_xg) DESC
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
        AVG(avg_xg_for)                    AS avg_xg_for,
        AVG(avg_goals_scored)              AS avg_goals_scored,
        NULLIF(AVG(avg_ppda), 0)           AS avg_ppda,
        AVG(avg_deep_completions)          AS avg_deep_completions,
        NULLIF(AVG(avg_xg_against), 0)     AS avg_xg_against
    FROM {_DATASET}.mart_winning_profiles
    WHERE {season_sql} AND {league_sql} AND match_result = 'win'
    GROUP BY league
    ORDER BY league
    """
    return run_query(sql)


# ── render ─────────────────────────────────────────────────────────────────────

def render():
    st.title("Key Findings")

    # ── Global filters ────────────────────────────────────────────────────────
    st.markdown("#### Filters")
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
            "Season mode",
            options=["Single season", "Last 5 seasons avg", "Custom range"],
            horizontal=True,
            key="findings_season_mode",
        )

    if season_mode == "Single season":
        selected_season = st.select_slider(
            "Season", options=ALL_SEASONS, value="2023",
            key="findings_single_season",
        )
        season_sql   = f"season = '{selected_season}'"
        season_label = f"Season {selected_season}"

    elif season_mode == "Last 5 seasons avg":
        season_sql   = "season IN ('2019','2020','2021','2022','2023')"
        season_label = "5-season avg (2019–2023)"

    else:
        col_a, col_b = st.columns(2)
        with col_a:
            s_from = st.selectbox("From", ALL_SEASONS, index=0, key="s_from")
        with col_b:
            s_to = st.selectbox("To", ALL_SEASONS, index=len(ALL_SEASONS) - 1, key="s_to")
        valid = [s for s in ALL_SEASONS if s_from <= s <= s_to]
        if not valid:
            st.warning("'From' season must be ≤ 'To' season.")
            return
        season_sql   = f"season IN ({','.join(repr(s) for s in valid)})"
        season_label = f"Avg {s_from}–{s_to}"

    if not selected_leagues:
        st.warning("Select at least one league to display charts.")
        return

    league_sql = f"league IN ({','.join(repr(l) for l in selected_leagues)})"

    # ── Load winning profiles once — reused across Charts 1-4 and Adv Chart A ─
    st.markdown("---")
    with st.spinner("Loading winning profiles…"):
        try:
            wp = _winning_profiles(season_sql, league_sql)
        except Exception as e:
            st.error(f"Winning profiles query failed: {e}")
            wp = pd.DataFrame()

    if wp.empty:
        st.warning("No data for the selected filters.")
    else:
        result_order = ["win", "draw", "loss"]
        wp["_sort"] = wp["match_result"].map({"win": 0, "draw": 1, "loss": 2})
        wp = wp.sort_values(["league", "_sort"]).drop(columns="_sort")

        # ── Chart 1 — xG Created ──────────────────────────────────────────────
        st.markdown("### xG Created by Result")
        st.caption(f"Avg xG generated per match — {season_label}")

        fig = go.Figure()
        for result in result_order:
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
        fig.update_layout(barmode="group", **_base_layout())
        st.plotly_chart(fig, use_container_width=True)

        wins   = wp[wp["match_result"] == "win"]
        losses = wp[wp["match_result"] == "loss"]
        if not wins.empty and not losses.empty:
            avg_win_xg  = wins["avg_xg_for"].mean()
            avg_loss_xg = losses["avg_xg_for"].mean()
            pct = ((avg_win_xg - avg_loss_xg) / avg_loss_xg * 100) if avg_loss_xg else 0
            st.info(
                f"Winning teams generate **{avg_win_xg:.2f} avg xG** vs "
                f"**{avg_loss_xg:.2f}** for losing teams across selected leagues "
                f"— a **{pct:.0f}% difference**. xG is the strongest single "
                "predictor of match result in this dataset."
            )

        # ── Chart 2 — Finishing Efficiency ───────────────────────────────────
        st.markdown("### Finishing Efficiency")
        st.caption(
            f"Goals scored ÷ xG created per result — {season_label}. "
            "Values above 1.0 mean the team outscored their expected goals. "
            "★ marks leagues where winning teams exceed a 1.2 ratio."
        )

        eff = wp.copy()
        eff["ratio"] = (
            eff["avg_goals_scored"] / eff["avg_xg_for"].replace(0, float("nan"))
        ).round(3)

        fig2 = go.Figure()
        for result in result_order:
            sub = eff[eff["match_result"] == result]
            if sub.empty:
                continue
            fig2.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["ratio"],
                marker_color=RESULT_COLORS[result],
                text=sub["ratio"].round(2),
                textposition="outside",
            ))

        annotations = []
        for _, row in eff[(eff["match_result"] == "win") & (eff["ratio"] > 1.2)].iterrows():
            annotations.append(dict(
                x=LEAGUE_LABELS.get(row["league"], row["league"]),
                y=row["ratio"] + 0.06,
                text="★",
                showarrow=False,
                font=dict(size=18, color="#f4a261"),
            ))

        fig2.add_hline(
            y=1.0, line_dash="dash", line_color="#94a3b8",
            annotation_text="xG = Goals (1.0)",
            annotation_position="top right",
        )
        layout2 = _base_layout()
        layout2["barmode"]     = "group"
        layout2["annotations"] = annotations
        fig2.update_layout(**layout2)
        st.plotly_chart(fig2, use_container_width=True)

        # ── Chart 3 — Pressing Intensity (inverted PPDA) ─────────────────────
        st.markdown("### Pressing Intensity")
        st.caption(
            f"Derived from PPDA (Passes Allowed Per Defensive Action) — {season_label}. "
            "**Lower raw PPDA = more pressing.** Chart shows 10 ÷ PPDA so that "
            "taller bars = more intense press. Hover for raw PPDA values."
        )

        press = wp.copy()
        press["intensity"] = (10 / press["avg_ppda"].replace(0, float("nan"))).round(3)

        fig3 = go.Figure()
        for result in result_order:
            sub = press[press["match_result"] == result]
            if sub.empty:
                continue
            fig3.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["intensity"],
                marker_color=RESULT_COLORS[result],
                text=sub["avg_ppda"].round(2),
                texttemplate="PPDA: %{text}",
                textposition="outside",
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"Result: {result}<br>"
                    "Pressing intensity: %{y:.3f}<br>"
                    "Raw PPDA: %{text}<extra></extra>"
                ),
            ))
        layout3 = _base_layout()
        layout3["barmode"]      = "group"
        layout3["yaxis_title"]  = "Pressing Intensity (10 / PPDA)"
        fig3.update_layout(**layout3)
        st.plotly_chart(fig3, use_container_width=True)
        st.info(
            "Winning teams press slightly harder (lower PPDA), but the gap is only ~13% "
            "vs ~90% for xG. Pressing is a supporting factor, not the primary driver. "
            "Note: PPDA trend over 2014–2023 shows teams pressing LESS over time while "
            "xG creation is rising — suggesting the league is evolving away from pressing."
        )

        # ── Chart 4 — Deep Completions ────────────────────────────────────────
        st.markdown("### Dangerous Area Penetration")
        st.caption(
            f"Avg passes completed into the danger zone (deep completions) "
            f"per match — {season_label}."
        )

        fig4 = go.Figure()
        for result in result_order:
            sub = wp[wp["match_result"] == result]
            if sub.empty:
                continue
            fig4.add_trace(go.Bar(
                name=result.capitalize(),
                x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                y=sub["avg_deep_completions"].round(2),
                marker_color=RESULT_COLORS[result],
                text=sub["avg_deep_completions"].round(1),
                textposition="outside",
            ))
        layout4 = _base_layout()
        layout4["barmode"]     = "group"
        layout4["yaxis_title"] = "Avg Deep Completions"
        fig4.update_layout(**layout4)
        st.plotly_chart(fig4, use_container_width=True)

    # ── League Standings (own independent filters) ────────────────────────────
    st.markdown("---")
    st.markdown("### League Standings")

    col_sl, col_ss = st.columns([2, 3])
    with col_sl:
        standings_league = st.selectbox(
            "League",
            options=ALL_LEAGUES,
            format_func=lambda x: LEAGUE_LABELS[x],
            index=0,
            key="standings_league",
        )
    with col_ss:
        standings_season_mode = st.radio(
            "Season",
            options=["Single season", "Last 5 seasons avg", "Custom range"],
            horizontal=True,
            key="standings_season_mode",
        )

    if standings_season_mode == "Single season":
        standings_season = st.select_slider(
            "Season", options=ALL_SEASONS, value="2023",
            key="standings_single_season",
        )
        s_season_sql   = f"season = '{standings_season}'"
        s_season_label = f"Season {standings_season}"

    elif standings_season_mode == "Last 5 seasons avg":
        s_season_sql   = "season IN ('2019','2020','2021','2022','2023')"
        s_season_label = "5-season avg (2019–2023)"

    else:
        col_sa, col_sb = st.columns(2)
        with col_sa:
            ss_from = st.selectbox("From", ALL_SEASONS, index=0, key="ss_from")
        with col_sb:
            ss_to = st.selectbox("To", ALL_SEASONS, index=len(ALL_SEASONS) - 1, key="ss_to")
        valid_s = [s for s in ALL_SEASONS if ss_from <= s <= ss_to]
        if not valid_s:
            st.warning("'From' must be ≤ 'To'.")
            valid_s = ALL_SEASONS
        s_season_sql   = f"season IN ({','.join(repr(s) for s in valid_s)})"
        s_season_label = f"Avg {ss_from}–{ss_to}"

    s_league_sql = f"league = '{standings_league}'"
    st.caption(f"Showing: {LEAGUE_LABELS[standings_league]} — {s_season_label}")

    with st.spinner("Loading standings…"):
        try:
            standings = _league_standings(s_season_sql, s_league_sql)
        except Exception as e:
            st.error(f"Standings query failed: {e}")
            standings = pd.DataFrame()

    if standings.empty:
        st.warning(
            "No standings data for the selected league and season. "
            "Check that the pipeline has been run for this combination."
        )
    else:
        st.dataframe(
            standings,
            column_config={
                "team":          st.column_config.TextColumn("Team"),
                "league":        st.column_config.TextColumn("League"),
                "wins":          st.column_config.NumberColumn("W",       format="%.1f"),
                "draws":         st.column_config.NumberColumn("D",       format="%.1f"),
                "losses":        st.column_config.NumberColumn("L",       format="%.1f"),
                "goals_for":     st.column_config.NumberColumn("GF",      format="%.1f"),
                "goals_against": st.column_config.NumberColumn("GA",      format="%.1f"),
                "total_xg_for":  st.column_config.NumberColumn("xG For",  format="%.2f"),
                "avg_ppda":      st.column_config.NumberColumn("PPDA",    format="%.2f"),
                "points":        st.column_config.NumberColumn("Pts",     format="%.1f"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "PPDA: lower = more pressing. "
            "Values are averages when multiple seasons are selected."
        )

    # ── Top Players (global filters) ──────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### Top 10 Players by xG — {season_label}")

    with st.spinner("Loading player data…"):
        try:
            players = _top_players(season_sql, league_sql)
        except Exception as e:
            st.error(f"Player query failed: {e}")
            players = pd.DataFrame()

    if players.empty:
        st.warning("No player data for the selected filters.")
    else:
        players["league_name"] = players["league"].map(LEAGUE_LABELS)
        st.dataframe(
            players[["player_name", "team", "league_name", "season",
                      "total_xg", "total_goals", "xg_per_90", "match_appearances"]],
            column_config={
                "player_name":       st.column_config.TextColumn("Player"),
                "team":              st.column_config.TextColumn("Team"),
                "league_name":       st.column_config.TextColumn("League"),
                "season":            st.column_config.TextColumn("Season"),
                "total_xg":          st.column_config.NumberColumn("Total xG", format="%.3f"),
                "total_goals":       st.column_config.NumberColumn("Goals",     format="%d"),
                "xg_per_90":         st.column_config.NumberColumn("xG / 90",   format="%.3f"),
                "match_appearances": st.column_config.NumberColumn("Apps",      format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Showing: {season_label} · Leagues: {', '.join(LEAGUE_LABELS.get(l, l) for l in selected_leagues)}")

    # ── Advanced Insights ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Advanced Insights: Finishing, Concentration & Profiles")

    # ── Advanced Chart A — Goals vs xG Differential ───────────────────────────
    st.markdown("#### Goals vs xG Differential by Result")
    st.caption(f"Avg (goals scored − xG created) per match — {season_label}")

    if not wp.empty:
        gxd = wp.copy()
        gxd["goals_xg_diff"] = (gxd["avg_goals_scored"] - gxd["avg_xg_for"]).round(4)

        fig_a = go.Figure()
        for result in result_order:
            sub = gxd[gxd["match_result"] == result]
            if sub.empty:
                continue
            fig_a.add_trace(go.Bar(
                name=result.capitalize(),
                y=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
                x=sub["goals_xg_diff"],
                orientation="h",
                marker_color=RESULT_COLORS[result],
                hovertemplate="%{y}<br>Goals − xG: %{x:.3f}<extra>%{fullData.name}</extra>",
            ))
        layout_a = _base_layout(height=420)
        layout_a["barmode"]  = "group"
        layout_a["xaxis"]    = dict(
            title="Goals − xG (avg per match)",
            range=[-0.6, 0.6],
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor="#94a3b8",
            gridcolor="#e5e7eb",
        )
        layout_a["yaxis"]         = dict(title="", gridcolor="#e5e7eb")
        layout_a["legend_title"]  = "Result"
        fig_a.update_layout(**layout_a)
        st.plotly_chart(fig_a, use_container_width=True)
        st.info(
            "Winning teams consistently **outscore their xG** (positive diff); "
            "losing teams underperform it (negative diff). This finishing differential "
            "compounds the underlying xG gap between wins and losses."
        )
    else:
        st.warning("No winning profiles data available for the selected filters.")

    # ── Advanced Chart B — Goal Concentration vs Win Rate ─────────────────────
    st.markdown("#### Goal Concentration vs Win Rate")
    st.caption(f"Top scorer's share of team goals vs season win rate — {season_label}")

    with st.spinner("Loading concentration data…"):
        try:
            conc = _goal_concentration(season_sql, league_sql)
        except Exception as e:
            st.error(f"Goal concentration query failed: {e}")
            conc = pd.DataFrame()

    if conc.empty or len(conc) < 3:
        st.warning("Not enough data — expand the season range or select more leagues.")
    else:
        conc = conc.copy()
        conc["top_scorer_pct"] = (conc["top_scorer_share"] * 100).round(1)
        conc["win_rate_pct"]   = (conc["win_rate"] * 100).round(1)
        conc["marker_size"]    = (conc["team_total_goals"].fillna(0) / 5).clip(lower=4)

        fig_b = go.Figure()
        for league_key in selected_leagues:
            sub = conc[conc["league"] == league_key]
            if sub.empty:
                continue
            fig_b.add_trace(go.Scatter(
                x=sub["top_scorer_pct"],
                y=sub["win_rate_pct"],
                mode="markers",
                name=LEAGUE_LABELS.get(league_key, league_key),
                marker=dict(
                    size=sub["marker_size"],
                    color=LEAGUE_COLORS.get(league_key, "#888"),
                    opacity=0.7,
                    line=dict(width=1, color="#ffffff"),
                ),
                customdata=sub[["team", "season", "top_scorer_pct", "win_rate_pct"]].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Season: %{customdata[1]}<br>"
                    "Top scorer share: %{customdata[2]:.1f}%<br>"
                    "Win rate: %{customdata[3]:.1f}%<extra></extra>"
                ),
            ))

        layout_b = _base_layout(height=480)
        layout_b["xaxis"]        = dict(title="Top scorer's share of team goals (%)", gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
        layout_b["yaxis"]        = dict(title="Season win rate (%)", gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
        layout_b["legend_title"] = "League"
        fig_b.update_layout(**layout_b)
        fig_b.add_vline(
            x=30, line_dash="dash", line_color="#94a3b8",
            annotation_text="30% threshold",
            annotation_position="top right",
        )
        st.plotly_chart(fig_b, use_container_width=True)
        st.info(
            "Goal concentration (how much one player dominates team scoring) shows "
            "**no clear relationship with win rate**. Teams with a dominant striker "
            "and teams with distributed goals win at similar rates — total xG quality "
            "is the stronger driver."
        )

    # ── Advanced Chart C — Winning Profile Radar ─────────────────────────────
    st.markdown("#### Winning Profile Radar Chart (per League)")
    st.caption(f"Normalised (0-100) winning team attributes by league — {season_label}")

    with st.spinner("Loading radar data…"):
        try:
            radar_raw = _winning_radar(season_sql, league_sql)
        except Exception as e:
            st.error(f"Radar query failed: {e}")
            radar_raw = pd.DataFrame()

    if not radar_raw.empty:
        radar = radar_raw.copy()

        # Compute derived dimensions — invalid inputs (NaN/0/inf) become NaN
        radar["_xg_created"]  = radar["avg_xg_for"].where(
            radar["avg_xg_for"].notna() & (radar["avg_xg_for"] > 0)
        )
        radar["_finishing"]   = (
            radar["avg_goals_scored"] / radar["avg_xg_for"].replace(0, float("nan"))
        ).where(lambda s: s.notna() & (s > 0))
        radar["_pressing"]    = (10.0 / radar["avg_ppda"]).where(
            radar["avg_ppda"].notna() & (radar["avg_ppda"] > 0)
        )
        radar["_territorial"] = radar["avg_deep_completions"].where(
            radar["avg_deep_completions"].notna() & (radar["avg_deep_completions"] > 0)
        )
        radar["_defensive"]   = (1.0 / radar["avg_xg_against"]).where(
            radar["avg_xg_against"].notna() & (radar["avg_xg_against"] > 0)
        )

        _dim_cols = {
            "xG Created":      "_xg_created",
            "Finishing Eff":   "_finishing",
            "Pressing":        "_pressing",
            "Territorial":     "_territorial",
            "Defensive":       "_defensive",
        }

        # Data quality warnings
        missing_pairs = []
        for _, row in radar.iterrows():
            lbl = LEAGUE_LABELS.get(row["league"], row["league"])
            for dim, col in _dim_cols.items():
                if pd.isna(row[col]):
                    missing_pairs.append(f"{lbl} – {dim}")
        if missing_pairs:
            st.warning("Missing data (excluded from radar): " + ", ".join(missing_pairs))

        # Exclude leagues with fewer than 3 valid dimensions
        valid_counts = {
            row["league"]: sum(1 for col in _dim_cols.values() if not pd.isna(row[col]))
            for _, row in radar.iterrows()
        }
        excluded = [l for l, c in valid_counts.items() if c < 3]
        if excluded:
            excl_labels = ", ".join(LEAGUE_LABELS.get(l, l) for l in excluded)
            st.warning(f"Excluded (fewer than 3 valid dimensions): {excl_labels}")
            radar = radar[~radar["league"].isin(excluded)]

        # Normalise each dimension 0-100 across leagues
        for dim, col in _dim_cols.items():
            radar[col + "_norm"] = _minmax(radar[col])

        dim_labels_list = list(_dim_cols.keys())
        norm_cols_list  = [c + "_norm" for c in _dim_cols.values()]

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
            fig_c = go.Figure()
            for _, row in radar[radar["league"].isin(radar_selected)].iterrows():
                vals = [row[c] for c in norm_cols_list]
                vals_closed   = [None if pd.isna(v) else v for v in vals] + [
                    None if pd.isna(vals[0]) else vals[0]
                ]
                labels_closed = dim_labels_list + [dim_labels_list[0]]
                color = LEAGUE_COLORS.get(row["league"], "#888888")
                fig_c.add_trace(go.Scatterpolar(
                    r=vals_closed,
                    theta=labels_closed,
                    fill="toself",
                    name=LEAGUE_LABELS.get(row["league"], row["league"]),
                    line=dict(color=color),
                    fillcolor=color,
                    opacity=0.4,
                ))

            layout_c = _base_layout(height=520)
            layout_c["polar"] = dict(
                bgcolor="#ffffff",
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    gridcolor="#e5e7eb",
                    linecolor="#cbd5e1",
                ),
                angularaxis=dict(
                    gridcolor="#e5e7eb",
                    linecolor="#cbd5e1",
                ),
            )
            layout_c["showlegend"] = True
            fig_c.update_layout(**layout_c)
            st.plotly_chart(fig_c, use_container_width=True)
            st.info(
                "**EPL and Bundesliga** winning profiles are driven by pressing intensity "
                "and xG creation. **Serie A** winners lean on defensive solidity — lower "
                "xG conceded is their primary differentiator. **xG creation + finishing "
                "efficiency** is the universal constant across all five leagues."
            )
    elif not radar_raw.empty is False:
        st.error("Radar query returned no rows for winning teams in the selected filters.")
