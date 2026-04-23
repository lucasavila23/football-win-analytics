import sys
import os
import importlib.util
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

_bq_path = os.path.join(os.path.dirname(__file__), "..", "data", "bq_client.py")
_bq_spec = importlib.util.spec_from_file_location("bq_client", _bq_path)
_bq_mod  = importlib.util.module_from_spec(_bq_spec)
_bq_spec.loader.exec_module(_bq_mod)
run_query = _bq_mod.run_query

from pipeline.config import GCP_PROJECT_ID

_DATASET = f"`{GCP_PROJECT_ID}.marts`"

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
RESULT_COLORS = {"win": "#2ecc71", "draw": "#f39c12", "loss": "#e74c3c"}
ALL_LEAGUES  = list(LEAGUE_COLORS.keys())
ALL_SEASONS  = ["2014","2015","2016","2017","2018","2019","2020","2021","2022","2023"]

# Fixed absolute ranges per radar dimension — prevents tiny inter-league differences
# from being stretched to the full 0–100 scale (the flaw in min-max normalisation).
_RADAR_RANGES = {
    "_xg_created":  (0.5, 2.0),
    "_finishing":   (0.7, 1.5),
    "_pressing":    (0.6, 2.0),
    "_territorial": (4.0, 16.0),
    "_defensive":   (0.4, 1.5),
}


def _base_layout(height: int = 420) -> dict:
    return dict(
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        font=dict(color="#111111", family="sans-serif"),
        height=height, margin=dict(t=20, b=40, l=60, r=20),
        xaxis=dict(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb"),
        yaxis=dict(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb"),
    )


def _fixed_norm(val, lo: float, hi: float):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return max(0.0, min(100.0, (val - lo) / (hi - lo) * 100))


# ── Query functions ────────────────────────────────────────────────────────────

def _winning_profiles(season_sql: str, league_sql: str, multi_season: bool = False) -> pd.DataFrame:
    sql = f"""
    SELECT
        league, match_result,
        AVG(avg_xg_for)           AS avg_xg_for,
        AVG(avg_xg_against)       AS avg_xg_against,
        AVG(avg_goals_scored)     AS avg_goals_scored,
        AVG(avg_goals_conceded)   AS avg_goals_conceded,
        AVG(avg_ppda)             AS avg_ppda,
        AVG(avg_opponent_ppda)    AS avg_opponent_ppda,
        AVG(avg_deep_completions) AS avg_deep_completions,
        AVG(avg_np_xg_for)        AS avg_np_xg_for,
        SUM(matches)              AS sample_size
    FROM {_DATASET}.mart_winning_profiles
    WHERE {season_sql} AND {league_sql}
    GROUP BY league, match_result
    ORDER BY league, match_result
    """
    return run_query(sql)


def _league_standings(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT team, league, wins, draws, losses,
           goals_for, goals_against, total_xg_for, avg_ppda, points
    FROM {_DATASET}.mart_league_standings
    WHERE {season_sql} AND {league_sql}
    ORDER BY points DESC, goals_for DESC
    LIMIT 40
    """
    return run_query(sql)


def _top_players(season_sql: str, league_sql: str, multi_season: bool = False) -> pd.DataFrame:
    if multi_season:
        sql = f"""
        SELECT player_name, team, league,
               SUM(total_xg) AS total_xg, SUM(total_goals) AS total_goals,
               AVG(xg_per_90) AS xg_per_90, SUM(match_appearances) AS match_appearances
        FROM {_DATASET}.mart_player_performance
        WHERE {season_sql} AND {league_sql}
        GROUP BY player_name, team, league
        ORDER BY SUM(total_xg) DESC
        LIMIT 10
        """
    else:
        sql = f"""
        SELECT player_name, team, league, season,
               total_xg, total_goals, xg_per_90, match_appearances
        FROM {_DATASET}.mart_player_performance
        WHERE {season_sql} AND {league_sql}
        ORDER BY total_xg DESC
        LIMIT 10
        """
    return run_query(sql)


def _goal_concentration(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    WITH player_goals AS (
        SELECT team, league, season,
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
    SELECT p.team, p.league, p.season,
           SAFE_DIVIDE(p.top_scorer_goals, NULLIF(p.team_total_goals, 0)) AS top_scorer_share,
           s.win_rate, p.team_total_goals
    FROM player_goals p
    JOIN standings s ON p.team = s.team AND p.league = s.league AND p.season = s.season
    WHERE p.team_total_goals > 0
    ORDER BY p.league, p.team
    """
    return run_query(sql)


def _winning_radar(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT league,
           AVG(avg_xg_for)                AS avg_xg_for,
           AVG(avg_goals_scored)          AS avg_goals_scored,
           NULLIF(AVG(avg_ppda), 0)       AS avg_ppda,
           AVG(avg_deep_completions)      AS avg_deep_completions,
           NULLIF(AVG(avg_xg_against), 0) AS avg_xg_against
    FROM {_DATASET}.mart_winning_profiles
    WHERE {season_sql} AND {league_sql} AND match_result = 'win'
    GROUP BY league
    ORDER BY league
    """
    return run_query(sql)


def _home_advantage(season_sql: str, league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT match_result, is_home,
           SUM(matches)                    AS total_matches,
           ROUND(AVG(avg_xg_for),   3)     AS xg_for,
           ROUND(AVG(avg_ppda),     3)     AS ppda,
           ROUND(AVG(avg_goals_scored), 3) AS goals_scored
    FROM {_DATASET}.mart_winning_profiles
    WHERE {season_sql} AND {league_sql}
    GROUP BY match_result, is_home
    ORDER BY CASE match_result WHEN 'win' THEN 1 WHEN 'draw' THEN 2 ELSE 3 END, is_home DESC
    """
    return run_query(sql)


def _league_variation(league_sql: str) -> pd.DataFrame:
    sql = f"""
    SELECT league,
           ROUND(AVG(avg_xg_for),  3) AS avg_xg_for,
           ROUND(AVG(avg_ppda),    3) AS avg_ppda,
           ROUND(AVG(avg_xg_diff), 3) AS avg_xg_diff,
           SUM(matches)               AS win_matches
    FROM {_DATASET}.mart_winning_profiles
    WHERE match_result = 'win' AND {league_sql}
    GROUP BY league
    ORDER BY avg_xg_for DESC
    """
    return run_query(sql)


def _temporal_trend() -> pd.DataFrame:
    sql = f"""
    SELECT season,
           ROUND(AVG(total_xg_for),        2) AS avg_xg_for,
           ROUND(AVG(total_xg_against),     2) AS avg_xg_against,
           ROUND(AVG(avg_ppda),             2) AS avg_ppda,
           ROUND(AVG(avg_deep_completions), 1) AS avg_deep,
           ROUND(AVG(win_rate),             3) AS avg_win_rate
    FROM {_DATASET}.mart_league_standings
    GROUP BY season
    ORDER BY season
    """
    return run_query(sql)


def _team_rankings() -> dict:
    xg_creators = run_query(f"""
    SELECT team, league,
           ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
           ROUND(AVG(points),       0) AS avg_points,
           ROUND(AVG(win_rate),     3) AS avg_win_rate
    FROM {_DATASET}.mart_league_standings
    GROUP BY team, league
    ORDER BY avg_xg_for DESC
    LIMIT 5
    """)
    best_finishing = run_query(f"""
    SELECT team, league,
           ROUND(AVG(total_xg_for),                               2) AS avg_xg_for,
           ROUND(AVG(total_xg_against),                           2) AS avg_xg_against,
           ROUND(AVG(total_xg_for) - AVG(total_xg_against),       2) AS xg_diff,
           ROUND(AVG(points),   0) AS avg_points,
           ROUND(AVG(win_rate), 3) AS avg_win_rate
    FROM {_DATASET}.mart_league_standings
    GROUP BY team, league
    ORDER BY xg_diff DESC
    LIMIT 5
    """)
    best_pressers = run_query(f"""
    SELECT team, league,
           ROUND(AVG(avg_ppda), 2) AS avg_ppda,
           ROUND(AVG(points),   0) AS avg_points,
           ROUND(AVG(win_rate), 3) AS avg_win_rate
    FROM {_DATASET}.mart_league_standings
    GROUP BY team, league
    ORDER BY avg_ppda ASC
    LIMIT 5
    """)
    xg_goals_ratio = run_query(f"""
    SELECT team, league,
           ROUND(AVG(goals_for),    1) AS avg_goals,
           ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
           ROUND(SAFE_DIVIDE(AVG(goals_for), NULLIF(AVG(total_xg_for), 0)), 3) AS goals_per_xg,
           ROUND(AVG(win_rate),     3) AS avg_win_rate
    FROM {_DATASET}.mart_league_standings
    GROUP BY team, league
    ORDER BY goals_per_xg DESC
    LIMIT 5
    """)
    return {"xg": xg_creators, "finishing": best_finishing, "pressing": best_pressers, "ratio": xg_goals_ratio}


def _outliers() -> dict:
    unlucky = run_query(f"""
    SELECT team, league,
           ROUND(AVG(total_xg_for), 2) AS avg_xg_for,
           ROUND(AVG(win_rate),     3) AS avg_win_rate,
           ROUND(AVG(points),       0) AS avg_points
    FROM {_DATASET}.mart_league_standings
    GROUP BY team, league
    HAVING AVG(total_xg_for) > 50 AND AVG(win_rate) < 0.35
    ORDER BY avg_xg_for DESC
    LIMIT 5
    """)
    return {"unlucky": unlucky}


def _three_pillars_teams() -> pd.DataFrame:
    return run_query(f"""
    WITH base AS (
        SELECT team, league,
               AVG(total_xg_for)                         AS avg_xg_for,
               AVG(total_xg_for) - AVG(total_xg_against) AS xg_diff,
               AVG(avg_ppda)                             AS avg_ppda,
               AVG(win_rate)                             AS avg_win_rate,
               AVG(points)                               AS avg_points
        FROM {_DATASET}.mart_league_standings
        GROUP BY team, league
    ),
    ranked AS (
        SELECT *,
               RANK() OVER (ORDER BY avg_xg_for DESC) AS rank_xg,
               RANK() OVER (ORDER BY xg_diff     DESC) AS rank_xg_diff,
               RANK() OVER (ORDER BY avg_ppda     ASC)  AS rank_pressing
        FROM base
    )
    SELECT team, league,
           ROUND(avg_xg_for,   2) AS avg_xg_for,
           ROUND(xg_diff,      2) AS xg_diff,
           ROUND(avg_ppda,     2) AS avg_ppda,
           ROUND(avg_win_rate, 3) AS win_rate,
           ROUND(avg_points,   0) AS avg_points,
           rank_xg, rank_xg_diff, rank_pressing,
           (rank_xg + rank_xg_diff + rank_pressing) AS combined_rank
    FROM ranked
    ORDER BY combined_rank ASC
    LIMIT 5
    """)


# ── render ─────────────────────────────────────────────────────────────────────

def render():
    st.title("Key Findings")

    st.markdown("#### Filters")
    col_l, col_s = st.columns([3, 2])

    with col_l:
        selected_leagues = st.multiselect(
            "Leagues", options=ALL_LEAGUES, default=ALL_LEAGUES,
            format_func=lambda x: LEAGUE_LABELS[x], key="findings_leagues",
        )
    with col_s:
        season_mode = st.radio(
            "Season mode",
            options=["Single season", "Last 5 seasons avg", "Custom range"],
            horizontal=True, key="findings_season_mode",
        )

    if season_mode == "Single season":
        selected_season = st.select_slider(
            "Season", options=ALL_SEASONS, value="2023", key="findings_single_season",
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

    league_sql   = f"league IN ({','.join(repr(l) for l in selected_leagues)})"
    result_order = ["win", "draw", "loss"]

    # ── Load winning profiles once (reused across multiple charts) ────────────
    st.markdown("---")
    with st.spinner("Loading winning profiles…"):
        try:
            wp = _winning_profiles(season_sql, league_sql, multi_season=(season_mode != "Single season"))
        except Exception as e:
            st.error(f"Winning profiles query failed: {e}")
            wp = pd.DataFrame()

    if wp.empty:
        st.warning("No data for the selected filters.")
        return

    wp["_sort"] = wp["match_result"].map({"win": 0, "draw": 1, "loss": 2})
    wp = wp.sort_values(["league", "_sort"]).drop(columns="_sort")

    # ── Chart 1 — xG Created by Result ───────────────────────────────────────
    st.markdown("### xG Created by Result")
    st.caption(f"Avg xG generated per match — {season_label}")

    fig1 = go.Figure()
    for result in result_order:
        sub = wp[wp["match_result"] == result]
        if sub.empty:
            continue
        fig1.add_trace(go.Bar(
            name=result.capitalize(),
            x=[LEAGUE_LABELS.get(l, l) for l in sub["league"]],
            y=sub["avg_xg_for"].round(3),
            marker_color=RESULT_COLORS[result],
            text=sub["avg_xg_for"].round(2),
            textposition="outside",
        ))
    fig1.update_layout(barmode="group", **_base_layout())
    st.plotly_chart(fig1, use_container_width=True)

    wins   = wp[wp["match_result"] == "win"]
    losses = wp[wp["match_result"] == "loss"]
    if not wins.empty and not losses.empty:
        avg_win_xg  = wins["avg_xg_for"].mean()
        avg_loss_xg = losses["avg_xg_for"].mean()
        pct = ((avg_win_xg - avg_loss_xg) / avg_loss_xg * 100) if avg_loss_xg else 0
        st.info(
            f"Winning teams generate **{avg_win_xg:.2f} avg xG** vs "
            f"**{avg_loss_xg:.2f}** for losing teams — a **{pct:.0f}% difference**. "
            "xG is the strongest single predictor of match result in this dataset."
        )

    # ── Advanced Insights ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Advanced Insights: Finishing, Concentration & Profiles")

    # Adv A — Goals vs xG Differential
    st.markdown("#### Goals vs xG Differential by Result")
    st.caption(f"Avg (goals scored − xG created) per match — {season_label}")

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
    layout_a["barmode"] = "group"
    layout_a["xaxis"]   = dict(title="Goals − xG (avg per match)", range=[-0.6, 0.6],
                               zeroline=True, zerolinewidth=2, zerolinecolor="#94a3b8",
                               gridcolor="#e5e7eb")
    layout_a["yaxis"]        = dict(title="", gridcolor="#e5e7eb")
    layout_a["legend_title"] = "Result"
    fig_a.update_layout(**layout_a)
    st.plotly_chart(fig_a, use_container_width=True)
    st.info(
        "Winning teams consistently **outscore their xG** (positive diff); "
        "losing teams underperform it (negative diff). This finishing differential "
        "compounds the underlying xG gap between wins and losses."
    )

    # Adv B — Goal Concentration vs Win Rate
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
        conc["team_label"]     = conc["team"].str.title()

        fig_b = go.Figure()
        for league_key in selected_leagues:
            sub = conc[conc["league"] == league_key]
            if sub.empty:
                continue
            fig_b.add_trace(go.Scatter(
                x=sub["top_scorer_pct"], y=sub["win_rate_pct"],
                mode="markers",
                name=LEAGUE_LABELS.get(league_key, league_key),
                marker=dict(size=sub["marker_size"], color=LEAGUE_COLORS.get(league_key, "#888"),
                            opacity=0.7, line=dict(width=1, color="#ffffff")),
                customdata=sub[["team_label", "season", "top_scorer_pct", "win_rate_pct"]].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>Season: %{customdata[1]}<br>"
                    "Top scorer share: %{customdata[2]:.1f}%<br>"
                    "Win rate: %{customdata[3]:.1f}%<extra></extra>"
                ),
            ))
        layout_b = _base_layout(height=480)
        layout_b["xaxis"]        = dict(title="Top scorer's share of team goals (%)", gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
        layout_b["yaxis"]        = dict(title="Season win rate (%)", gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
        layout_b["legend_title"] = "League"
        fig_b.update_layout(**layout_b)
        fig_b.add_vline(x=30, line_dash="dash", line_color="#94a3b8",
                        annotation_text="30% threshold", annotation_position="top right")
        st.plotly_chart(fig_b, use_container_width=True)
        st.info(
            "Goal concentration shows **no clear relationship with win rate**. "
            "Teams with a dominant striker and teams with distributed goals win at similar rates — "
            "total xG quality is the stronger driver."
        )

    # Adv C — Winning Profile Radar
    st.markdown("#### Winning Profile Radar Chart (per League)")
    st.caption(
        f"Fixed-scale (0–100) winning team attributes by league — {season_label}. "
        "Ranges are absolute, not relative, to prevent amplifying small differences."
    )

    with st.spinner("Loading radar data…"):
        try:
            radar_raw = _winning_radar(season_sql, league_sql)
        except Exception as e:
            st.error(f"Radar query failed: {e}")
            radar_raw = pd.DataFrame()

    if not radar_raw.empty:
        radar = radar_raw.copy()
        radar["_xg_created"]  = radar["avg_xg_for"].where(radar["avg_xg_for"].notna() & (radar["avg_xg_for"] > 0))
        radar["_finishing"]   = (radar["avg_goals_scored"] / radar["avg_xg_for"].replace(0, float("nan"))).where(lambda s: s.notna() & (s > 0))
        radar["_pressing"]    = (10.0 / radar["avg_ppda"]).where(radar["avg_ppda"].notna() & (radar["avg_ppda"] > 0))
        radar["_territorial"] = radar["avg_deep_completions"].where(radar["avg_deep_completions"].notna() & (radar["avg_deep_completions"] > 0))
        radar["_defensive"]   = (1.0 / radar["avg_xg_against"]).where(radar["avg_xg_against"].notna() & (radar["avg_xg_against"] > 0))

        _dim_cols = {
            "xG Created":  "_xg_created",
            "Finishing":   "_finishing",
            "Pressing":    "_pressing",
            "Territorial": "_territorial",
            "Defensive":   "_defensive",
        }

        missing_pairs = []
        for _, row in radar.iterrows():
            lbl = LEAGUE_LABELS.get(row["league"], row["league"])
            for dim, col in _dim_cols.items():
                if pd.isna(row[col]):
                    missing_pairs.append(f"{lbl} – {dim}")
        if missing_pairs:
            st.warning("Missing data (excluded from radar): " + ", ".join(missing_pairs))

        valid_counts = {row["league"]: sum(1 for col in _dim_cols.values() if not pd.isna(row[col])) for _, row in radar.iterrows()}
        excluded = [l for l, c in valid_counts.items() if c < 3]
        if excluded:
            st.warning(f"Excluded (< 3 valid dimensions): {', '.join(LEAGUE_LABELS.get(l, l) for l in excluded)}")
            radar = radar[~radar["league"].isin(excluded)]

        for dim, col in _dim_cols.items():
            lo, hi = _RADAR_RANGES[col]
            radar[col + "_norm"] = radar[col].apply(lambda v, lo=lo, hi=hi: _fixed_norm(v, lo, hi))

        dim_labels_list = list(_dim_cols.keys())
        norm_cols_list  = [c + "_norm" for c in _dim_cols.values()]

        all_radar_leagues = sorted(radar["league"].unique())
        radar_selected = st.multiselect(
            "Select leagues to display", options=all_radar_leagues, default=all_radar_leagues,
            format_func=lambda x: LEAGUE_LABELS.get(x, x), key="radar_leagues",
        )

        if radar_selected:
            fig_c = go.Figure()
            for _, row in radar[radar["league"].isin(radar_selected)].iterrows():
                vals = [row[c] for c in norm_cols_list]
                vals_closed   = vals + [vals[0]]
                labels_closed = dim_labels_list + [dim_labels_list[0]]
                color = LEAGUE_COLORS.get(row["league"], "#888888")
                fig_c.add_trace(go.Scatterpolar(
                    r=vals_closed, theta=labels_closed, fill="toself",
                    name=LEAGUE_LABELS.get(row["league"], row["league"]),
                    line=dict(color=color), fillcolor=color, opacity=0.4,
                ))
            layout_c = _base_layout(height=520)
            layout_c["polar"] = dict(
                bgcolor="#ffffff",
                radialaxis=dict(visible=True, range=[0, 100], gridcolor="#e5e7eb", linecolor="#cbd5e1"),
                angularaxis=dict(gridcolor="#e5e7eb", linecolor="#cbd5e1"),
            )
            layout_c["showlegend"] = True
            fig_c.update_layout(**layout_c)
            st.plotly_chart(fig_c, use_container_width=True)
            st.info(
                "**EPL and Bundesliga** winning profiles are driven by pressing intensity "
                "and xG creation. **Serie A** winners lean on defensive solidity. "
                "**xG creation + finishing efficiency** is the universal constant across all five leagues."
            )

    # ── Chart 2 — Finishing Efficiency ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### Finishing Efficiency")
    st.caption(
        f"Goals scored ÷ xG created per result — {season_label}. "
        "Values above 1.0 mean the team outscored their expected goals. "
        "★ marks leagues where winning teams exceed a 1.2 ratio."
    )

    eff = wp.copy()
    eff["ratio"] = (eff["avg_goals_scored"] / eff["avg_xg_for"].replace(0, float("nan"))).round(3)

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
            x=LEAGUE_LABELS.get(row["league"], row["league"]), y=row["ratio"] + 0.06,
            text="★", showarrow=False, font=dict(size=18, color="#f4a261"),
        ))
    fig2.add_hline(y=1.0, line_dash="dash", line_color="#94a3b8",
                   annotation_text="xG = Goals (1.0)", annotation_position="top right")
    layout2 = _base_layout()
    layout2["barmode"]     = "group"
    layout2["annotations"] = annotations
    fig2.update_layout(**layout2)
    st.plotly_chart(fig2, use_container_width=True)

    # ── Chart 3 — Pressing Intensity ─────────────────────────────────────────
    st.markdown("### Pressing Intensity")
    st.caption(
        f"Derived from PPDA — {season_label}. "
        "**Lower PPDA = more pressing.** Chart shows 10 ÷ PPDA: taller bars = more intense press."
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
    layout3["barmode"]     = "group"
    layout3["yaxis_title"] = "Pressing Intensity (10 / PPDA)"
    fig3.update_layout(**layout3)
    st.plotly_chart(fig3, use_container_width=True)
    st.info(
        "Winning teams press slightly harder (lower PPDA), but the gap is only ~13% "
        "vs ~90% for xG. Pressing is a supporting factor, not the primary driver."
    )

    # ── Chart 4 — Deep Completions ────────────────────────────────────────────
    st.markdown("### Dangerous Area Penetration")
    st.caption(f"Avg passes into the danger zone (deep completions) per match — {season_label}.")

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

    # ── League Standings — single season only ─────────────────────────────────
    st.markdown("---")
    st.markdown("### League Standings")

    col_sl, col_ss = st.columns([2, 3])
    with col_sl:
        standings_league = st.selectbox(
            "League", options=ALL_LEAGUES, format_func=lambda x: LEAGUE_LABELS[x],
            index=0, key="standings_league",
        )
    with col_ss:
        standings_season = st.select_slider(
            "Season", options=ALL_SEASONS, value="2023", key="standings_single_season",
        )

    s_season_sql = f"season = '{standings_season}'"
    s_league_sql = f"league = '{standings_league}'"
    st.caption(f"Showing: {LEAGUE_LABELS[standings_league]} — Season {standings_season}")

    with st.spinner("Loading standings…"):
        try:
            standings = _league_standings(s_season_sql, s_league_sql)
        except Exception as e:
            st.error(f"Standings query failed: {e}")
            standings = pd.DataFrame()

    if standings.empty:
        st.warning("No standings data for the selected league and season.")
    else:
        standings = standings.copy()
        standings["team"] = standings["team"].str.title()
        st.dataframe(
            standings,
            column_config={
                "team":          st.column_config.TextColumn("Team"),
                "league":        st.column_config.TextColumn("League"),
                "wins":          st.column_config.NumberColumn("W",      format="%.0f"),
                "draws":         st.column_config.NumberColumn("D",      format="%.0f"),
                "losses":        st.column_config.NumberColumn("L",      format="%.0f"),
                "goals_for":     st.column_config.NumberColumn("GF",     format="%.0f"),
                "goals_against": st.column_config.NumberColumn("GA",     format="%.0f"),
                "total_xg_for":  st.column_config.NumberColumn("xG For", format="%.2f"),
                "avg_ppda":      st.column_config.NumberColumn("PPDA",   format="%.2f"),
                "points":        st.column_config.NumberColumn("Pts",    format="%.0f"),
            },
            use_container_width=True, hide_index=True,
        )
        st.caption("PPDA: lower = more pressing.")

    # ── Top 10 Players — scatter plot ─────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### Top 10 Players by xG — {season_label}")

    with st.spinner("Loading player data…"):
        try:
            players = _top_players(season_sql, league_sql, multi_season=(season_mode != "Single season"))
        except Exception as e:
            st.error(f"Player query failed: {e}")
            players = pd.DataFrame()

    if players.empty:
        st.warning("No player data for the selected filters.")
    else:
        players = players.copy()
        players["player_label"]   = players["player_name"].str.title()
        players["team_label"]     = players["team"].str.title()
        players["goals_xg_ratio"] = (players["total_goals"] / players["total_xg"].replace(0, float("nan"))).round(2)

        fig_p = go.Figure()
        for league_key in selected_leagues:
            sub = players[players["league"] == league_key]
            if sub.empty:
                continue
            fig_p.add_trace(go.Scatter(
                x=sub["total_xg"], y=sub["total_goals"],
                mode="markers+text",
                name=LEAGUE_LABELS.get(league_key, league_key),
                text=sub["player_label"],
                textposition="top center",
                textfont=dict(size=9),
                marker=dict(size=14, color=LEAGUE_COLORS.get(league_key, "#888"),
                            opacity=0.85, line=dict(width=1, color="#ffffff")),
                customdata=sub[["player_label", "team_label", "match_appearances", "goals_xg_ratio"]].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                    "xG: %{x:.2f} · Goals: %{y}<br>"
                    "Apps: %{customdata[2]} · Goals/xG: %{customdata[3]:.2f}<extra></extra>"
                ),
            ))

        max_val = max(players["total_xg"].max(), players["total_goals"].max()) * 1.05
        fig_p.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                        line=dict(dash="dash", color="#94a3b8", width=1))
        layout_p = _base_layout(height=480)
        layout_p["xaxis"]        = dict(title="Total xG", gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
        layout_p["yaxis"]        = dict(title="Total Goals", gridcolor="#e5e7eb", zerolinecolor="#e5e7eb")
        layout_p["legend_title"] = "League"
        fig_p.update_layout(**layout_p)
        st.plotly_chart(fig_p, use_container_width=True)
        st.caption(
            "Diagonal = xG equals goals. Points above outperform their xG; below = underperforming. "
            f"Leagues: {', '.join(LEAGUE_LABELS.get(l, l) for l in selected_leagues)}"
        )

    # ── Home Advantage — grouped bar chart ────────────────────────────────────
    st.markdown("---")
    st.markdown("### Home Advantage: Does It Distort the Findings?")
    with st.spinner("Loading home/away breakdown…"):
        try:
            ha = _home_advantage(season_sql, league_sql)
        except Exception as e:
            st.error(f"Home advantage query failed: {e}")
            ha = pd.DataFrame()

    if not ha.empty:
        ha = ha.copy()
        ha["location"] = ha["is_home"].apply(lambda x: "Home" if x else "Away")
        fig_ha = go.Figure()
        for loc, color in [("Home", "#3498db"), ("Away", "#e67e22")]:
            sub = ha[ha["location"] == loc].copy()
            sub["_sort"] = sub["match_result"].map({"win": 0, "draw": 1, "loss": 2})
            sub = sub.sort_values("_sort")
            fig_ha.add_trace(go.Bar(
                name=loc,
                x=[r.capitalize() for r in sub["match_result"]],
                y=sub["xg_for"].round(3),
                marker_color=color,
                text=sub["xg_for"].round(2),
                textposition="outside",
                hovertemplate=f"<b>{loc}</b><br>Result: %{{x}}<br>Avg xG For: %{{y:.3f}}<extra></extra>",
            ))
        layout_ha = _base_layout()
        layout_ha["barmode"]     = "group"
        layout_ha["yaxis_title"] = "Avg xG For"
        fig_ha.update_layout(**layout_ha)
        st.plotly_chart(fig_ha, use_container_width=True)
        st.info(
            "Home teams create slightly more xG but the win/loss pattern holds in both "
            "contexts. Home advantage **amplifies** the effect — it doesn't reverse it."
        )

    # ── League Variation ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Is the Winning Formula Universal Across Leagues?")
    with st.spinner("Loading league variation…"):
        try:
            lv = _league_variation(league_sql)
        except Exception as e:
            st.error(f"League variation query failed: {e}")
            lv = pd.DataFrame()

    if not lv.empty:
        lv["league_name"] = lv["league"].map(LEAGUE_LABELS)
        st.dataframe(
            lv[["league_name", "avg_xg_for", "avg_ppda", "avg_xg_diff", "win_matches"]],
            column_config={
                "league_name": st.column_config.TextColumn("League"),
                "avg_xg_for":  st.column_config.NumberColumn("Avg xG For (wins)", format="%.3f"),
                "avg_ppda":    st.column_config.NumberColumn("Avg PPDA (wins)",   format="%.2f"),
                "avg_xg_diff": st.column_config.NumberColumn("xG Differential",   format="%.3f"),
                "win_matches": st.column_config.NumberColumn("Win Matches",       format="%d"),
            },
            use_container_width=True, hide_index=True,
        )
        st.info(
            "All five leagues show an xG differential of ~0.85 separating wins from losses. "
            "**The winning formula is not league-specific — it's football-universal.**"
        )

    # ── Temporal Trend — pressing shown as 10/PPDA ────────────────────────────
    st.markdown("---")
    st.markdown("### How Has Football Evolved Over 10 Seasons?")
    with st.spinner("Loading temporal trend…"):
        try:
            tt = _temporal_trend()
        except Exception as e:
            st.error(f"Temporal trend query failed: {e}")
            tt = pd.DataFrame()

    if not tt.empty:
        tt = tt.copy()
        tt["pressing_intensity"] = (10 / tt["avg_ppda"].replace(0, float("nan"))).round(3)

        fig_tt = go.Figure()
        fig_tt.add_trace(go.Scatter(
            x=tt["season"], y=tt["avg_xg_for"],
            name="Avg xG For", mode="lines+markers",
            line=dict(color="#2ecc71", width=2), marker=dict(size=6), yaxis="y1",
        ))
        fig_tt.add_trace(go.Scatter(
            x=tt["season"], y=tt["pressing_intensity"],
            name="Pressing Intensity (10 / PPDA)", mode="lines+markers",
            line=dict(color="#e74c3c", width=2, dash="dash"), marker=dict(size=6), yaxis="y2",
        ))
        layout_tt = _base_layout(height=420)
        layout_tt["xaxis"]  = dict(title="Season", gridcolor="#e5e7eb")
        layout_tt["yaxis"]  = dict(title=dict(text="Avg xG For", font=dict(color="#2ecc71")),
                                   tickfont=dict(color="#2ecc71"), gridcolor="#e5e7eb")
        layout_tt["yaxis2"] = dict(
            title=dict(text="Pressing Intensity (10 / PPDA)", font=dict(color="#e74c3c")),
            tickfont=dict(color="#e74c3c"), overlaying="y", side="right", showgrid=False,
        )
        layout_tt["legend"] = dict(x=0.01, y=0.99)
        fig_tt.update_layout(**layout_tt)
        st.plotly_chart(fig_tt, use_container_width=True)
        st.info(
            "xG created has risen steadily (2014→2023) while pressing intensity has "
            "**decreased**. Win rates stayed flat. "
            "**Modern football is being won by better chance creation, not more pressing.**"
        )

    # ── Elite Teams ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Elite Teams — Who Does It Best?")
    with st.spinner("Loading team rankings…"):
        try:
            rankings = _team_rankings()
        except Exception as e:
            st.error(f"Team rankings query failed: {e}")
            rankings = None

    if rankings is not None:
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 xG Creation", "📊 xG Differential", "⚡ Pressing", "⚽ xG / Goals Ratio"])
        with tab1:
            if not rankings["xg"].empty:
                df = rankings["xg"].copy(); df["team"] = df["team"].str.title()
                st.dataframe(df, use_container_width=True, hide_index=True)
        with tab2:
            if not rankings["finishing"].empty:
                df = rankings["finishing"].copy(); df["team"] = df["team"].str.title()
                st.dataframe(df, use_container_width=True, hide_index=True)
        with tab3:
            if not rankings["pressing"].empty:
                df = rankings["pressing"].copy(); df["team"] = df["team"].str.title()
                st.dataframe(df, use_container_width=True, hide_index=True)
        with tab4:
            if not rankings["ratio"].empty:
                df = rankings["ratio"].copy(); df["team"] = df["team"].str.title()
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption("Goals per xG: teams that consistently finish above their expected goals across all seasons.")
        st.info(
            "Elite teams (Barcelona, Man City, Bayern) lead on xG creation, xG differential, "
            "and pressing — they win because they're **complete**. "
            "Finishing efficiency (goals/xG) is noisiest at season level; "
            "the real gap appears at match level (1.30 goals/xG in wins vs 0.59 in losses)."
        )

    # ── Three Pillars — Best Teams Overall ────────────────────────────────────
    st.markdown("---")
    st.markdown("### Best Teams Across All Three Pillars")
    st.caption("Combined ranking: xG creation + xG differential + pressing intensity (all seasons)")

    with st.spinner("Loading three-pillar rankings…"):
        try:
            tp = _three_pillars_teams()
        except Exception as e:
            st.error(f"Three pillars query failed: {e}")
            tp = pd.DataFrame()

    if not tp.empty:
        tp = tp.copy()
        tp["team"]        = tp["team"].str.title()
        tp["league_name"] = tp["league"].map(LEAGUE_LABELS)
        st.dataframe(
            tp[["team", "league_name", "avg_xg_for", "xg_diff", "avg_ppda",
                "win_rate", "avg_points", "rank_xg", "rank_xg_diff", "rank_pressing", "combined_rank"]],
            column_config={
                "team":          st.column_config.TextColumn("Team"),
                "league_name":   st.column_config.TextColumn("League"),
                "avg_xg_for":    st.column_config.NumberColumn("Avg xG For",      format="%.2f"),
                "xg_diff":       st.column_config.NumberColumn("xG Differential", format="%.2f"),
                "avg_ppda":      st.column_config.NumberColumn("Avg PPDA",        format="%.2f"),
                "win_rate":      st.column_config.NumberColumn("Win Rate",        format="%.3f"),
                "avg_points":    st.column_config.NumberColumn("Avg Points",      format="%d"),
                "rank_xg":       st.column_config.NumberColumn("Rank xG",         format="%d"),
                "rank_xg_diff":  st.column_config.NumberColumn("Rank xG Diff",    format="%d"),
                "rank_pressing": st.column_config.NumberColumn("Rank Pressing",   format="%d"),
                "combined_rank": st.column_config.NumberColumn("Combined Rank",   format="%d"),
            },
            use_container_width=True, hide_index=True,
        )
        st.info(
            "Combined rank = sum of individual pillar ranks (lower is better). "
            "Teams at the top excel across **all three dimensions** — not just one."
        )

    # ── Outliers ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Outliers — Teams That Break the Formula")
    with st.spinner("Loading outliers…"):
        try:
            outliers = _outliers()
        except Exception as e:
            st.error(f"Outliers query failed: {e}")
            outliers = None

    if outliers is not None and not outliers["unlucky"].empty:
        ol = outliers["unlucky"].copy()
        ol["team"] = ol["team"].str.title()
        st.markdown("**High xG, Low Win Rate** *(unlucky/poor finishing)*")
        st.dataframe(ol, use_container_width=True, hide_index=True)
        st.info(
            "Teams like Brentford and Brighton create plenty of chances but finish poorly — "
            "trapped in mid-table despite strong xG numbers. Finishing efficiency matters."
        )

    st.caption(
        "Core charts respect the global league/season filters. "
        "Team rankings, outliers, and temporal trend use the full 10-season dataset (2014–2023)."
    )
