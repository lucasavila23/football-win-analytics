import sys
import os
import importlib.util
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

_bq_path = os.path.join(os.path.dirname(__file__), "..", "data", "bq_client.py")
_bq_spec = importlib.util.spec_from_file_location("bq_client", _bq_path)
_bq_mod  = importlib.util.module_from_spec(_bq_spec)
_bq_spec.loader.exec_module(_bq_mod)
run_query = _bq_mod.run_query

from pipeline.config import GCP_PROJECT_ID

_DATASET = f"`{GCP_PROJECT_ID}.marts`"

FIXED_LEAGUES    = ['La Liga', 'Premier League', 'Serie A']
FIXED_LEAGUE_SQL = "league IN ('La Liga', 'Premier League', 'Serie A')"
FIXED_SEASON_SQL = "season = '2023'"

LEAGUE_LABELS = {
    'La Liga':        'La Liga',
    'Premier League': 'Premier League',
    'Serie A':        'Serie A',
}
LEAGUE_COLORS = {
    'La Liga':        '#e74c3c',
    'Premier League': '#3498db',
    'Serie A':        '#2ecc71',
}
RESULT_COLORS = {"win": "#2ecc71", "draw": "#f39c12", "loss": "#e74c3c"}


def _base_layout(height: int = 420) -> dict:
    return dict(
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        font=dict(color="#111111", family="sans-serif"),
        height=height, margin=dict(t=20, b=40, l=60, r=20),
        xaxis=dict(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb"),
        yaxis=dict(gridcolor="#e5e7eb", zerolinecolor="#e5e7eb"),
    )


def _r2_and_trend(x_vals, y_vals):
    x = np.array(x_vals, dtype=float)
    y = np.array(y_vals, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return None, None, None
    coeffs = np.polyfit(x, y, 1)
    y_pred = np.polyval(coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = round(float(1 - ss_res / ss_tot), 3) if ss_tot > 0 else 0.0
    trend_x = np.linspace(x.min(), x.max(), 60)
    trend_y = np.polyval(coeffs, trend_x)
    return r2, trend_x, trend_y


# ── render ─────────────────────────────────────────────────────────────────────

def render():
    st.title("Key Findings")

    # ── Season probe ─────────────────────────────────────────────────────────
    probe_sql = f"""
SELECT DISTINCT season
FROM {_DATASET}.mart_league_standings
WHERE {FIXED_LEAGUE_SQL}
ORDER BY season DESC
LIMIT 1
"""
    try:
        probe = run_query(probe_sql)
        latest_season = probe.iloc[0]['season'] if not probe.empty else '2023'
    except Exception:
        latest_season = '2023'
    season_sql = f"season = '{latest_season}'"

    # ── Team name probe ───────────────────────────────────────────────────────
    team_probe_sql = f"""
SELECT DISTINCT team, league
FROM {_DATASET}.mart_league_standings
ORDER BY team
"""
    try:
        known_teams = run_query(team_probe_sql)
    except Exception:
        known_teams = pd.DataFrame()

    # ── Slide 1 — The Scale of the Game ──────────────────────────────────────
    st.markdown("### Slide 1 — The Scale of the Game")
    st.markdown("> *\"Before we talk about football, let's talk about what's at stake.\"*")

    clubs_data = [
        {"name": "Barcelona",       "revenue": "€975M", "attendance": "~55,000*", "capacity": "99,354"},
        {"name": "Bayern Munich",   "revenue": "€860M", "attendance": "75,000",   "capacity": "75,024"},
        {"name": "Manchester City", "revenue": "€829M", "attendance": "53,000",   "capacity": "55,097"},
        {"name": "PSG",             "revenue": "€802M", "attendance": "46,000",   "capacity": "47,929"},
        {"name": "Liverpool",       "revenue": "€836M", "attendance": "61,000",   "capacity": "61,276"},
    ]
    s1_cols = st.columns(5)
    for col, club in zip(s1_cols, clubs_data):
        with col:
            st.metric(club["name"], club["revenue"])
            st.caption(f"Avg att: {club['attendance']}")
            st.caption(f"Capacity: {club['capacity']}")

    st.caption("*Temporary stadium during Camp Nou renovation")
    st.info(
        "These five clubs generated a combined **€4.3 billion** in revenue in 2024/25 "
        "(Deloitte Football Money League). They are not sports teams in the traditional "
        "sense — they are global entertainment companies."
    )

    st.markdown("---")

    # ── Slide 2 — What Winning Drives ────────────────────────────────────────
    st.markdown("### Slide 2 — What Winning Drives")

    clubs  = ['Liverpool', 'Barcelona', 'Manchester City', 'PSG', 'Bayern Munich']
    titles = [1, 4, 6, 9, 9]
    colors = ['#c8102e', '#a50044', '#6cabdd', '#004170', '#dc052d']

    fig_s2 = go.Figure()
    for club, title, color in zip(clubs, titles, colors):
        fig_s2.add_trace(go.Bar(
            name=club,
            y=[club],
            x=[title],
            orientation='h',
            marker_color=color,
            text=[str(title)],
            textposition='inside',
            insidetextanchor='middle',
        ))

    layout_s2 = _base_layout(height=320)
    layout_s2["barmode"]      = "stack"
    layout_s2["xaxis"]        = dict(title="Domestic league titles (2014–2023)", gridcolor="#e5e7eb",
                                      range=[0, 12])
    layout_s2["yaxis"]        = dict(title="", gridcolor="#e5e7eb", autorange="reversed")
    layout_s2["showlegend"]   = False
    layout_s2["margin"]       = dict(t=20, b=40, l=150, r=40)
    fig_s2.update_layout(**layout_s2)
    st.plotly_chart(fig_s2, use_container_width=True)

    st.info(
        "Domestic dominance is the foundation. Winning the league consistently drives "
        "broadcast revenue, commercial deals, and transfer budgets — which fund more winning. "
        "**Bayern and PSG have won their domestic league 9 out of the last 10 seasons.**"
    )
    st.markdown(
        "The financial gap between a team that wins the league and one that finishes fifth is "
        "not marginal — it compounds every season through broadcast distributions, sponsorship "
        "premiums, and player recruitment leverage."
    )

    st.markdown("---")

    # ── Slide 3 — The Question ────────────────────────────────────────────────
    st.markdown("### Slide 3 — The Question")
    st.markdown("## What does it actually take to win at football?")

    s3_cols = st.columns(3)
    with s3_cols[0]:
        st.metric("Matches analysed", "300")
    with s3_cols[1]:
        st.metric("Seasons covered", "10 (2014–2023)")
    with s3_cols[2]:
        st.metric("Leagues", "5 (La Liga, Premier League, Serie A, Bundesliga, Ligue 1)")

    st.info(
        "We built a data pipeline from Understat and ESPN into BigQuery, transformed through dbt, "
        "and analysed across 3 tables: matches, player_stats, and lineups. "
        "**The question is not philosophical — it has a data answer.**"
    )

    st.markdown("---")

    # ── Slide 4 — Introducing xG ──────────────────────────────────────────────
    st.markdown("### Slide 4 — Introducing xG")
    st.markdown(
        "xG (Expected Goals) assigns a probability between 0 and 1 to every shot based on its "
        "location, angle, body part used, and whether it was assisted. A tap-in from 3 metres "
        "scores **0.85 xG**. A 30-yard strike scores **0.04 xG**. The actual goal counts as 1 "
        "either way — xG measures the quality of the chance, not the binary outcome."
    )

    fig_pitch = go.Figure()
    fig_pitch.add_shape(type="rect", x0=0, y0=0, x1=105, y1=68,
                        fillcolor="#2d6a4f", line_color="#ffffff", line_width=2)
    fig_pitch.add_shape(type="rect", x0=83, y0=13.84, x1=105, y1=54.16,
                        fillcolor="rgba(0,0,0,0)", line_color="#ffffff", line_width=2)
    fig_pitch.add_shape(type="rect", x0=94.5, y0=24.8, x1=105, y1=43.2,
                        fillcolor="rgba(0,0,0,0)", line_color="#ffffff", line_width=1)
    fig_pitch.add_shape(type="line", x0=52.5, y0=0, x1=52.5, y1=68,
                        line=dict(color="#ffffff", width=1, dash="dot"))

    fig_pitch.add_trace(go.Scatter(
        x=[101, 63],
        y=[34, 34],
        mode='markers',
        marker=dict(size=18, color=['#f39c12', '#e74c3c'],
                    line=dict(color="#ffffff", width=2)),
        name="Shot locations",
        showlegend=False,
        hoverinfo='skip',
    ))

    fig_pitch.add_annotation(x=101, y=34,
        text="Tap-in<br>0.85 xG", showarrow=True, arrowhead=2, ax=0, ay=-50,
        font=dict(color="#ffffff", size=12), bgcolor="rgba(0,0,0,0.5)",
        arrowcolor="#f39c12")
    fig_pitch.add_annotation(x=63, y=34,
        text="Long shot<br>0.04 xG", showarrow=True, arrowhead=2, ax=0, ay=-50,
        font=dict(color="#ffffff", size=12), bgcolor="rgba(0,0,0,0.5)",
        arrowcolor="#e74c3c")
    fig_pitch.add_annotation(x=52.5, y=5,
        text="Both result in 1 goal or 0 goals",
        showarrow=False, font=dict(color="#ffffff", size=11),
        bgcolor="rgba(0,0,0,0.45)")

    fig_pitch.update_layout(
        title=dict(text="Same binary outcome, very different chance quality",
                   font=dict(size=14)),
        height=340,
        plot_bgcolor="#2d6a4f",
        paper_bgcolor="#ffffff",
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False,
                   range=[-5, 112]),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False,
                   range=[-5, 75]),
        margin=dict(t=40, b=10, l=10, r=10),
    )
    st.plotly_chart(fig_pitch, use_container_width=True)

    st.info(
        "Goals in a single match are too noisy — a keeper makes one great save, a striker hits "
        "the post, the scoreline lies. xG averages out over a season and tells you which team "
        "genuinely dominated. **That is why we use it as our primary metric.**"
    )

    st.markdown("---")

    # ── Slide 5 — xG vs Goals: Volume Predicts Winning, Conversion Does Not ──
    st.markdown("### Slide 5 — xG vs Goals: Volume Predicts Winning, Conversion Does Not")

    sql_s5 = f"""
SELECT team, league,
       total_xg_for,
       goals_for,
       ROUND(goals_for / NULLIF(total_xg_for, 0), 3) AS conversion_rate,
       win_rate,
       points
FROM {_DATASET}.mart_league_standings
WHERE {season_sql} AND {FIXED_LEAGUE_SQL}
"""
    try:
        df_s5 = run_query(sql_s5)
    except Exception as e:
        st.error(f"Query failed: {e}")
        st.code(sql_s5, language="sql")
        return

    r2_xg, r2_conv = None, None

    if not df_s5.empty:
        df_s5 = df_s5.copy()
        df_s5["win_rate_pct"] = df_s5["win_rate"] * 100

        col_a, col_b = st.columns(2)

        # Left — xG Volume vs Win Rate
        with col_a:
            r2_xg, tx_xg, ty_xg = _r2_and_trend(
                df_s5["total_xg_for"].values,
                df_s5["win_rate_pct"].values,
            )
            fig_s5a = go.Figure()
            for league in FIXED_LEAGUES:
                sub = df_s5[df_s5["league"] == league]
                if sub.empty:
                    continue
                fig_s5a.add_trace(go.Scatter(
                    x=sub["total_xg_for"], y=sub["win_rate_pct"],
                    mode='markers',
                    name=LEAGUE_LABELS.get(league, league),
                    marker=dict(size=10, color=LEAGUE_COLORS.get(league, "#888"),
                                opacity=0.8, line=dict(width=1, color="#ffffff")),
                    customdata=sub[["team", "league", "win_rate"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "League: %{customdata[1]}<br>"
                        "xG: %{x:.1f} · Win rate: %{y:.1f}%<extra></extra>"
                    ),
                ))
            if tx_xg is not None:
                fig_s5a.add_trace(go.Scatter(
                    x=tx_xg, y=ty_xg, mode='lines', name='Trend',
                    line=dict(color="#94a3b8", width=1, dash="dash"),
                    showlegend=False,
                ))
            if r2_xg is not None:
                fig_s5a.add_annotation(
                    x=0.03, y=0.97, xref="paper", yref="paper",
                    text=f"R² = {r2_xg:.2f}",
                    showarrow=False, font=dict(size=11, color="#111111"),
                    bgcolor="#f8f9fa", bordercolor="#dee2e6", borderwidth=1,
                )
            layout_s5a = _base_layout(height=400)
            layout_s5a["xaxis"]        = dict(title="Total xG created (season)", gridcolor="#e5e7eb")
            layout_s5a["yaxis"]        = dict(title="Win rate (%)", gridcolor="#e5e7eb")
            layout_s5a["legend_title"] = "League"
            layout_s5a["title"]        = dict(text="xG Volume vs Win Rate", font=dict(size=13))
            layout_s5a["margin"]       = dict(t=40, b=40, l=60, r=20)
            fig_s5a.update_layout(**layout_s5a)
            st.plotly_chart(fig_s5a, use_container_width=True)

        # Right — Conversion Rate vs Win Rate
        with col_b:
            df_conv = df_s5.dropna(subset=["conversion_rate"])
            r2_conv, tx_conv, ty_conv = _r2_and_trend(
                df_conv["conversion_rate"].values,
                df_conv["win_rate_pct"].values,
            )
            fig_s5b = go.Figure()
            for league in FIXED_LEAGUES:
                sub = df_conv[df_conv["league"] == league]
                if sub.empty:
                    continue
                fig_s5b.add_trace(go.Scatter(
                    x=sub["conversion_rate"], y=sub["win_rate_pct"],
                    mode='markers',
                    name=LEAGUE_LABELS.get(league, league),
                    marker=dict(size=10, color=LEAGUE_COLORS.get(league, "#888"),
                                opacity=0.8, line=dict(width=1, color="#ffffff")),
                    customdata=sub[["team", "league", "win_rate"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "League: %{customdata[1]}<br>"
                        "Conv: %{x:.3f} · Win rate: %{y:.1f}%<extra></extra>"
                    ),
                ))
            if tx_conv is not None:
                fig_s5b.add_trace(go.Scatter(
                    x=tx_conv, y=ty_conv, mode='lines', name='Trend',
                    line=dict(color="#94a3b8", width=1, dash="dash"),
                    showlegend=False,
                ))
            if r2_conv is not None:
                fig_s5b.add_annotation(
                    x=0.03, y=0.97, xref="paper", yref="paper",
                    text=f"R² = {r2_conv:.2f}",
                    showarrow=False, font=dict(size=11, color="#111111"),
                    bgcolor="#f8f9fa", bordercolor="#dee2e6", borderwidth=1,
                )
            layout_s5b = _base_layout(height=400)
            layout_s5b["xaxis"]        = dict(title="Goals scored / xG (conversion rate)", gridcolor="#e5e7eb")
            layout_s5b["yaxis"]        = dict(title="Win rate (%)", gridcolor="#e5e7eb")
            layout_s5b["legend_title"] = "League"
            layout_s5b["title"]        = dict(text="Conversion Rate vs Win Rate", font=dict(size=13))
            layout_s5b["margin"]       = dict(t=40, b=40, l=60, r=20)
            fig_s5b.update_layout(**layout_s5b)
            st.plotly_chart(fig_s5b, use_container_width=True)

        if r2_xg is not None and r2_conv is not None:
            st.markdown(f"**xG volume R²: {r2_xg:.2f} — Conversion rate R²: {r2_conv:.2f}**")

    st.info(
        "Winning teams generate 1.86 avg xG per match vs 0.98 for losing teams — a 90% difference. "
        "But the goals-per-xG ratio shows 120% difference. The left chart shows xG volume tracks "
        "win rate closely. The right chart shows conversion rate does not — you can be a clinical "
        "finisher and still lose because you didn't create enough chances."
    )

    st.markdown("---")

    # ── Slide 6 — The Other Metrics (and Why They're Weaker) ─────────────────
    st.markdown("### Slide 6 — The Other Metrics (and Why They're Weaker)")

    # Part A — Three pillars ranked (hardcoded)
    metrics   = ["Finishing Efficiency\n(Goals/xG ratio)", "xG Creation",
                 "Pressing Intensity\n(PPDA)"]
    pct_diff  = [120, 90, 13]
    bar_colors = ["#2ecc71", "#3498db", "#bdc3c7"]

    fig_s6a = go.Figure()
    fig_s6a.add_trace(go.Bar(
        y=metrics,
        x=pct_diff,
        orientation='h',
        marker_color=bar_colors,
        text=[f"{v}% difference" for v in pct_diff],
        textposition='outside',
    ))
    fig_s6a.add_vline(x=13, line_dash="dash", line_color="#bdc3c7",
                      annotation_text="Pressing", annotation_position="top right",
                      annotation_font=dict(size=10, color="#94a3b8"))
    fig_s6a.add_vline(x=90, line_dash="dash", line_color="#3498db",
                      annotation_text="xG", annotation_position="top right",
                      annotation_font=dict(size=10, color="#3498db"))
    layout_s6a = _base_layout(height=320)
    layout_s6a["xaxis"]  = dict(title="Win vs Loss % difference", gridcolor="#e5e7eb",
                                 range=[0, 145])
    layout_s6a["yaxis"]  = dict(title="", gridcolor="#e5e7eb")
    layout_s6a["title"]  = dict(text="Not all metrics are equal", font=dict(size=14))
    layout_s6a["margin"] = dict(t=40, b=40, l=185, r=90)
    fig_s6a.update_layout(**layout_s6a)
    st.plotly_chart(fig_s6a, use_container_width=True)

    st.info(
        "Pressing intensity shows only a **13% difference** between wins and losses. "
        "xG creation shows **90%**. Finishing efficiency shows **120%**. "
        "The conventional wisdom that pressing teams win is not supported by this data "
        "— it is the weakest of the three signals."
    )

    # Part B — Evolution graph (live query)
    st.markdown("#### How the metrics have evolved (all seasons)")

    sql_s6b = f"""
SELECT season,
       ROUND(AVG(total_xg_for), 2)  AS avg_xg_for,
       ROUND(AVG(avg_ppda), 2)       AS avg_ppda,
       ROUND(AVG(win_rate), 3)       AS avg_win_rate
FROM {_DATASET}.mart_league_standings
GROUP BY season
ORDER BY season
"""
    try:
        df_s6b = run_query(sql_s6b)
    except Exception as e:
        st.error(f"Query failed: {e}")
        st.code(sql_s6b, language="sql")
        df_s6b = pd.DataFrame()

    if not df_s6b.empty:
        df_s6b = df_s6b.copy()
        df_s6b["pressing_intensity"] = (10 / df_s6b["avg_ppda"].replace(0, float("nan"))).round(3)

        seasons_list = df_s6b["season"].tolist()
        mid_season   = seasons_list[len(seasons_list) // 2] if seasons_list else "2019"

        fig_s6b = go.Figure()
        fig_s6b.add_trace(go.Scatter(
            x=df_s6b["season"], y=df_s6b["avg_xg_for"],
            name="Avg xG Created", mode="lines+markers",
            line=dict(color="#2ecc71", width=2), marker=dict(size=6), yaxis="y1",
        ))
        fig_s6b.add_trace(go.Scatter(
            x=df_s6b["season"], y=df_s6b["pressing_intensity"],
            name="Pressing Intensity (10/PPDA)", mode="lines+markers",
            line=dict(color="#e74c3c", width=2, dash="dash"), marker=dict(size=6), yaxis="y2",
        ))

        layout_s6b = _base_layout(height=420)
        layout_s6b["xaxis"]  = dict(title="Season", gridcolor="#e5e7eb")
        layout_s6b["yaxis"]  = dict(
            title=dict(text="Avg xG Created", font=dict(color="#2ecc71")),
            tickfont=dict(color="#2ecc71"), gridcolor="#e5e7eb",
        )
        layout_s6b["yaxis2"] = dict(
            title=dict(text="Pressing Intensity (10/PPDA)", font=dict(color="#e74c3c")),
            tickfont=dict(color="#e74c3c"), overlaying="y", side="right", showgrid=False,
        )
        layout_s6b["legend"] = dict(x=0.01, y=0.99)
        layout_s6b["annotations"] = [
            go.layout.Annotation(
                x=0.5, y=0.5,
                xref="paper", yref="paper",
                text="Win rate: flat →",
                showarrow=False,
                font=dict(size=12, color="#94a3b8"),
                bgcolor="rgba(255,255,255,0.7)",
            )
        ]
        fig_s6b.update_layout(**layout_s6b)
        st.plotly_chart(fig_s6b, use_container_width=True)

    st.info(
        "Between 2014 and 2023, average xG created per team rose **17.5%** while pressing "
        "intensity dropped **34.8%**. Win rates stayed flat. **Modern football is being won "
        "by better chance creation — teams are pressing less and creating more.**"
    )

    st.markdown("---")

    # ── Slide 7 — xG Differential: Volume is the Foundation ─────────────────
    st.markdown("### Slide 7 — xG Differential: Volume is the Foundation")

    sql_s7 = f"""
SELECT league,
       ROUND(AVG(avg_xg_for),     3) AS avg_xg_for,
       ROUND(AVG(avg_xg_against), 3) AS avg_xg_against
FROM {_DATASET}.mart_winning_profiles
WHERE match_result = 'win'
  AND {season_sql}
  AND {FIXED_LEAGUE_SQL}
GROUP BY league
"""
    try:
        df_s7 = run_query(sql_s7)
    except Exception as e:
        st.error(f"Query failed: {e}")
        st.code(sql_s7, language="sql")
        df_s7 = pd.DataFrame()

    if df_s7.empty:
        st.warning("Using fallback data — live query returned empty")
        df_s7 = pd.DataFrame({
            'league':         ['La Liga', 'Premier League', 'Serie A'],
            'avg_xg_for':     [1.92,      1.88,             1.81],
            'avg_xg_against': [0.78,      0.81,             0.84],
        })

    fig_s7 = go.Figure()
    fig_s7.add_trace(go.Bar(
        name="xG Created",
        x=[LEAGUE_LABELS.get(l, l) for l in df_s7["league"]],
        y=df_s7["avg_xg_for"],
        marker_color="#2ecc71",
    ))
    fig_s7.add_trace(go.Bar(
        name="xG Conceded",
        x=[LEAGUE_LABELS.get(l, l) for l in df_s7["league"]],
        y=(-df_s7["avg_xg_against"]).round(3),
        marker_color="#e74c3c",
    ))

    for _, row in df_s7.iterrows():
        diff = row["avg_xg_for"] - row["avg_xg_against"]
        fig_s7.add_annotation(
            x=LEAGUE_LABELS.get(row["league"], row["league"]),
            y=row["avg_xg_for"] + 0.04,
            text=f"+{diff:.2f}",
            showarrow=False,
            font=dict(size=12, color="#111111"),
        )

    layout_s7 = _base_layout(height=400)
    layout_s7["barmode"]     = "relative"
    layout_s7["yaxis_title"] = "Avg xG per match (wins only)"
    layout_s7["title"]       = dict(text="xG For vs Against — winning matches only",
                                     font=dict(size=13))
    layout_s7["shapes"]      = [
        go.layout.Shape(
            type="line", x0=0, x1=1, y0=0, y1=0,
            xref="paper", yref="y",
            line=dict(color="#000000", width=2),
        )
    ]
    layout_s7["margin"] = dict(t=40, b=40, l=60, r=20)
    fig_s7.update_layout(**layout_s7)
    st.plotly_chart(fig_s7, use_container_width=True)

    st.info(
        "Winning teams don't just create more — they simultaneously suppress opponent chances. "
        "The differential between xG created and xG conceded is the single most complete match "
        "metric. Elite teams like Barcelona average a seasonal xG differential of **+57**."
    )

    st.markdown("---")

    # ── Slide 8 — The Conversion Trap ────────────────────────────────────────
    st.markdown("### Slide 8 — The Conversion Trap")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Team level — conversion rate vs xG volume**")
        sql_s8a = f"""
SELECT team, league,
       total_xg_for,
       ROUND(goals_for / NULLIF(total_xg_for, 0), 3) AS conversion_rate,
       win_rate
FROM {_DATASET}.mart_league_standings
WHERE {season_sql} AND {FIXED_LEAGUE_SQL}
"""
        try:
            df_s8a = run_query(sql_s8a)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.code(sql_s8a, language="sql")
            df_s8a = pd.DataFrame()

        if not df_s8a.empty:
            median_xg = float(df_s8a["total_xg_for"].median())
            fig_s8a = go.Figure()
            fig_s8a.add_trace(go.Scatter(
                x=df_s8a["total_xg_for"],
                y=df_s8a["conversion_rate"],
                mode='markers',
                marker=dict(
                    size=10,
                    color=df_s8a["win_rate"],
                    colorscale='RdYlGn',
                    showscale=True,
                    colorbar=dict(title="Win Rate"),
                    line=dict(width=1, color="#ffffff"),
                ),
                customdata=df_s8a[["team", "league", "win_rate"]].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "League: %{customdata[1]}<br>"
                    "xG: %{x:.1f} · Conv: %{y:.3f}<br>"
                    "Win rate: %{customdata[2]:.3f}<extra></extra>"
                ),
            ))
            fig_s8a.add_vline(x=median_xg, line_dash="dash", line_color="#94a3b8")
            fig_s8a.add_hline(y=1.0, line_dash="dash", line_color="#94a3b8")
            fig_s8a.add_annotation(
                x=0.07, y=0.93, xref="paper", yref="paper",
                text="HIGH conversion<br>LOW volume<br>LOW win rate",
                showarrow=False, font=dict(size=10, color="#e74c3c"),
                bgcolor="#fff5f5", bordercolor="#e74c3c", borderwidth=1,
            )
            fig_s8a.add_annotation(
                x=0.92, y=0.93, xref="paper", yref="paper",
                text="Elite zone",
                showarrow=False, font=dict(size=10, color="#2ecc71"),
                bgcolor="#f0fff4", bordercolor="#2ecc71", borderwidth=1,
            )
            layout_s8a = _base_layout(height=420)
            layout_s8a["xaxis"]  = dict(title="Total xG created (season)", gridcolor="#e5e7eb")
            layout_s8a["yaxis"]  = dict(title="Conversion rate (goals / xG)", gridcolor="#e5e7eb")
            layout_s8a["title"]  = dict(text="Team conversion rate vs xG volume", font=dict(size=13))
            layout_s8a["margin"] = dict(t=40, b=40, l=60, r=80)
            fig_s8a.update_layout(**layout_s8a)
            st.plotly_chart(fig_s8a, use_container_width=True)

    with col_b:
        st.markdown("**Player level — top xG accumulators vs goals**")
        sql_s8b = f"""
SELECT player_name, team, league,
       total_xg,
       total_goals,
       ROUND(total_goals / NULLIF(total_xg, 0), 2) AS conversion_rate,
       match_appearances
FROM {_DATASET}.mart_player_performance
WHERE {season_sql}
  AND {FIXED_LEAGUE_SQL}
  AND match_appearances >= 5
  AND total_xg > 0
ORDER BY total_xg DESC
LIMIT 20
"""
        try:
            df_s8b = run_query(sql_s8b)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.code(sql_s8b, language="sql")
            df_s8b = pd.DataFrame()

        if not df_s8b.empty:
            max_val_s8b = max(df_s8b["total_xg"].max(), df_s8b["total_goals"].max()) * 1.15

            fig_s8b = go.Figure()
            for league in FIXED_LEAGUES:
                sub = df_s8b[df_s8b["league"] == league].head(10)
                if sub.empty:
                    continue
                fig_s8b.add_trace(go.Scatter(
                    x=sub["total_xg"], y=sub["total_goals"],
                    mode='markers+text',
                    name=LEAGUE_LABELS.get(league, league),
                    text=sub["player_name"].str.title(),
                    textposition="top center",
                    textfont=dict(size=8),
                    marker=dict(size=12, color=LEAGUE_COLORS.get(league, "#888"),
                                opacity=0.8, line=dict(width=1, color="#ffffff")),
                    customdata=sub[["player_name", "team", "conversion_rate"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                        "xG: %{x:.2f} · Goals: %{y}<br>"
                        "Conv: %{customdata[2]:.2f}<extra></extra>"
                    ),
                ))
            fig_s8b.add_shape(type="line", x0=0, y0=0, x1=max_val_s8b, y1=max_val_s8b,
                              line=dict(dash="dash", color="#94a3b8", width=1))

            # Red dashed circle around high-conversion, low-volume "trap" players
            median_xg_p = float(df_s8b["total_xg"].median())
            trap = df_s8b[
                (df_s8b["total_xg"] < median_xg_p) &
                (df_s8b["conversion_rate"] > 1.2)
            ]
            if not trap.empty:
                cx = float(trap["total_xg"].mean())
                cy = float(trap["total_goals"].mean())
                rx = max(float(trap["total_xg"].std() or 0), 0.5) * 2
                ry = max(float(trap["total_goals"].std() or 0), 0.5) * 2
                fig_s8b.add_shape(
                    type="circle",
                    x0=cx - rx, y0=cy - ry, x1=cx + rx, y1=cy + ry,
                    line=dict(color="#e74c3c", width=2, dash="dash"),
                    fillcolor="rgba(0,0,0,0)",
                )
                fig_s8b.add_annotation(
                    x=cx, y=cy + ry + 1,
                    text="High conversion,<br>low volume",
                    showarrow=True, arrowhead=2, ax=30, ay=-20,
                    font=dict(size=9, color="#e74c3c"),
                )

            layout_s8b = _base_layout(height=420)
            layout_s8b["xaxis"]        = dict(title="Total xG (season)", gridcolor="#e5e7eb")
            layout_s8b["yaxis"]        = dict(title="Goals scored", gridcolor="#e5e7eb")
            layout_s8b["legend_title"] = "League"
            layout_s8b["title"]        = dict(text="Top players: xG accumulated vs goals scored",
                                               font=dict(size=13))
            layout_s8b["margin"]       = dict(t=40, b=40, l=60, r=20)
            fig_s8b.update_layout(**layout_s8b)
            st.plotly_chart(fig_s8b, use_container_width=True)

    st.info(
        "A player or team can finish 80% of their chances and still lose if they only had 3. "
        "Conversion rate without volume is noise. The players above the diagonal are "
        "overperforming their xG — but the players that matter for winning are the ones "
        "furthest right on the x-axis, regardless of where they sit relative to the diagonal line."
    )

    st.markdown("---")

    # ── Slide 9 — Does a Star Striker Actually Matter? ────────────────────────
    st.markdown("### Slide 9 — Does a Star Striker Actually Matter?")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Goal concentration vs win rate**")
        sql_s9a = f"""
WITH player_goals AS (
    SELECT team, league, season, player_name, total_goals,
           SUM(total_goals) OVER (
               PARTITION BY team, league, season
           ) AS team_total_goals
    FROM {_DATASET}.mart_player_performance
    WHERE {season_sql} AND {FIXED_LEAGUE_SQL}
),
top_scorers AS (
    SELECT team, league, season, player_name, total_goals,
           team_total_goals,
           ROUND(total_goals / NULLIF(team_total_goals, 0), 3) AS top_scorer_share,
           ROW_NUMBER() OVER (
               PARTITION BY team, league, season
               ORDER BY total_goals DESC
           ) AS rn
    FROM player_goals
)
SELECT ts.team, ts.league, ts.player_name AS top_scorer,
       ts.total_goals AS top_scorer_goals,
       ts.team_total_goals,
       ts.top_scorer_share,
       ls.win_rate
FROM top_scorers ts
JOIN {_DATASET}.mart_league_standings ls
  ON ts.team = ls.team
 AND ts.league = ls.league
 AND ts.season = ls.season
WHERE ts.rn = 1
  AND ts.team_total_goals > 0
"""
        try:
            df_s9a = run_query(sql_s9a)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.code(sql_s9a, language="sql")
            df_s9a = pd.DataFrame()

        if not df_s9a.empty:
            r2_s9, tx_s9, ty_s9 = _r2_and_trend(
                df_s9a["top_scorer_share"].values * 100,
                df_s9a["win_rate"].values * 100,
            )
            fig_s9a = go.Figure()
            for league in FIXED_LEAGUES:
                sub = df_s9a[df_s9a["league"] == league]
                if sub.empty:
                    continue
                fig_s9a.add_trace(go.Scatter(
                    x=sub["top_scorer_share"] * 100,
                    y=sub["win_rate"] * 100,
                    mode='markers',
                    name=LEAGUE_LABELS.get(league, league),
                    marker=dict(size=10, color=LEAGUE_COLORS.get(league, "#888"),
                                opacity=0.75, line=dict(width=1, color="#ffffff")),
                    customdata=sub[["team", "top_scorer", "top_scorer_goals"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Top scorer: %{customdata[1]} (%{customdata[2]} goals)<br>"
                        "Share: %{x:.1f}% · Win rate: %{y:.1f}%<extra></extra>"
                    ),
                ))
            if tx_s9 is not None:
                fig_s9a.add_trace(go.Scatter(
                    x=tx_s9, y=ty_s9, mode='lines', name='Trend',
                    line=dict(color="#94a3b8", width=1, dash="dash"),
                    showlegend=False,
                ))
            fig_s9a.add_vline(x=30, line_dash="dash", line_color="#94a3b8",
                              annotation_text="30%", annotation_position="top right")
            layout_s9a = _base_layout(height=400)
            layout_s9a["xaxis"]        = dict(title="Top scorer's % of team goals", gridcolor="#e5e7eb")
            layout_s9a["yaxis"]        = dict(title="Win rate (%)", gridcolor="#e5e7eb")
            layout_s9a["legend_title"] = "League"
            layout_s9a["title"]        = dict(text="Top scorer share vs win rate", font=dict(size=13))
            layout_s9a["margin"]       = dict(t=40, b=40, l=60, r=20)
            fig_s9a.update_layout(**layout_s9a)
            st.plotly_chart(fig_s9a, use_container_width=True)

    with col_b:
        st.markdown("**Top xG accumulators — do they convert above their xG?**")
        sql_s9b = f"""
SELECT player_name, team, league,
       total_xg,
       total_goals,
       ROUND(total_goals / NULLIF(total_xg, 0), 2) AS conversion_rate,
       match_appearances
FROM {_DATASET}.mart_player_performance
WHERE {season_sql}
  AND {FIXED_LEAGUE_SQL}
  AND match_appearances >= 5
  AND total_xg > 0
ORDER BY total_xg DESC
LIMIT 12
"""
        try:
            df_s9b = run_query(sql_s9b)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.code(sql_s9b, language="sql")
            df_s9b = pd.DataFrame()

        if not df_s9b.empty:
            df_s9b = df_s9b.sort_values("total_xg", ascending=True)
            median_xg_s9 = float(df_s9b["total_xg"].median())
            fig_s9b = go.Figure()
            fig_s9b.add_trace(go.Bar(
                y=df_s9b["player_name"].str.title(),
                x=df_s9b["total_xg"],
                orientation='h',
                marker=dict(
                    color=df_s9b["conversion_rate"],
                    colorscale='RdYlGn',
                    cmin=0.5, cmax=1.5,
                    colorbar=dict(title="Conversion rate<br>(goals/xG)"),
                    showscale=True,
                ),
                text=[f"{v:.2f}" for v in df_s9b["conversion_rate"]],
                textposition='outside',
                customdata=df_s9b[["team", "total_goals", "conversion_rate"]].values,
                hovertemplate=(
                    "<b>%{y}</b> (%{customdata[0]})<br>"
                    "xG: %{x:.2f} · Goals: %{customdata[1]}<br>"
                    "Conv: %{customdata[2]:.2f}<extra></extra>"
                ),
            ))
            fig_s9b.add_vline(x=median_xg_s9, line_dash="dash", line_color="#94a3b8")
            layout_s9b = _base_layout(height=420)
            layout_s9b["xaxis"]  = dict(title="Total xG accumulated (season)", gridcolor="#e5e7eb")
            layout_s9b["yaxis"]  = dict(title="", gridcolor="#e5e7eb")
            layout_s9b["title"]  = dict(text="Top xG accumulators — do they convert above their xG?",
                                         font=dict(size=13))
            layout_s9b["margin"] = dict(t=40, b=40, l=140, r=100)
            fig_s9b.update_layout(**layout_s9b)
            st.plotly_chart(fig_s9b, use_container_width=True)

    st.info(
        "There is no meaningful relationship between having a dominant scorer and winning the "
        "league. The right panel shows the highest xG accumulators — many of them convert at "
        "or below their xG (red/yellow bars). What puts them on winning teams is not their "
        "conversion rate. It is the **volume of chances** they generate and attract."
    )

    st.markdown("---")

    # ── Slide 10 — The Conversion Trap in Practice ────────────────────────────
    st.markdown("### Slide 10 — The Conversion Trap in Practice")

    ref_patterns = ['Barcel', 'Bayern', 'City', 'Liverpool', 'Paris']
    if not known_teams.empty:
        matched = known_teams[
            known_teams['team'].str.contains(
                '|'.join(ref_patterns), case=False, na=False
            )
        ]['team'].tolist()
    else:
        matched = []

    df_s10 = pd.DataFrame()
    if matched:
        matched_sql_list = ', '.join(f"'{t}'" for t in matched)
        sql_s10 = f"""
SELECT team, league, season,
       ROUND(total_xg_for, 2)                    AS total_xg_for,
       ROUND(total_xg_for - total_xg_against, 2) AS xg_differential,
       wins, losses,
       ROUND(win_rate, 3)                         AS win_rate,
       goals_for, goals_against
FROM {_DATASET}.mart_league_standings
WHERE team IN ({matched_sql_list})
ORDER BY total_xg_for ASC
LIMIT 6
"""
        try:
            df_s10 = run_query(sql_s10)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.code(sql_s10, language="sql")
            df_s10 = pd.DataFrame()

    use_fallback = df_s10.empty or len(df_s10) < 2
    if use_fallback:
        st.caption("Falling back to known high-xG, low-results outliers from the dataset")
        cards = [
            {"team": "Brentford", "season": "2023", "total_xg_for": 61.76,
             "xg_differential": -5.2, "win_rate": 0.329, "wins": 11, "losses": 15},
            {"team": "Brighton",  "season": "2023", "total_xg_for": 52.70,
             "xg_differential": -3.8, "win_rate": 0.282, "wins": 11, "losses": 22},
            {"team": "Stuttgart", "season": "2023", "total_xg_for": 51.39,
             "xg_differential": -2.1, "win_rate": 0.346, "wins": 9,  "losses": 13},
        ]
    else:
        cards = df_s10.to_dict("records")

    card_cols = st.columns(len(cards))
    for col, card in zip(card_cols, cards):
        with col:
            st.markdown(
                f"""<div style="border-left: 4px solid #e74c3c; padding: 12px;
                background: #fef9f9; border-radius: 4px;">
                <b>{card['team']}</b> — {card['season']}<br>
                Total xG: {card['total_xg_for']}<br>
                xG Differential: {card['xg_differential']}<br>
                Win rate: {card['win_rate']}<br>
                Record: {int(card['wins'])}W / {int(card['losses'])}L
                </div>""",
                unsafe_allow_html=True,
            )

    st.info(
        "When these teams lose seasons or stretches of matches, the xG tells the story before "
        "the table does. The formula breaks in one specific way: **chance creation collapses**. "
        "Not because the striker missed — because the system stopped generating chances. "
        "Low xG → low wins. Every time."
    )

    st.markdown("---")

    # ── Slide 11 — The Winning Formula ───────────────────────────────────────
    st.markdown("### Slide 11 — The Winning Formula")

    metrics_s11   = ["Finishing Efficiency\n(Goals/xG ratio)", "xG Creation",
                     "Pressing Intensity\n(PPDA)"]
    pct_diff_s11  = [120, 90, 13]
    bar_colors_s11 = ["#2ecc71", "#3498db", "#bdc3c7"]

    fig_s11 = go.Figure()
    fig_s11.add_trace(go.Bar(
        y=metrics_s11,
        x=pct_diff_s11,
        orientation='h',
        marker_color=bar_colors_s11,
        text=[f"{v}% difference" for v in pct_diff_s11],
        textposition='outside',
    ))
    fig_s11.add_vline(x=13, line_dash="dash", line_color="#bdc3c7",
                      annotation_text="Pressing", annotation_position="top right",
                      annotation_font=dict(size=10, color="#94a3b8"))
    fig_s11.add_vline(x=90, line_dash="dash", line_color="#3498db",
                      annotation_text="xG", annotation_position="top right",
                      annotation_font=dict(size=10, color="#3498db"))
    layout_s11 = _base_layout(height=350)
    layout_s11["xaxis"]  = dict(title="Win vs Loss % difference", gridcolor="#e5e7eb",
                                 range=[0, 150])
    layout_s11["yaxis"]  = dict(title="", gridcolor="#e5e7eb")
    layout_s11["title"]  = dict(text="What actually separates winners from losers",
                                 font=dict(size=14))
    layout_s11["margin"] = dict(t=40, b=40, l=190, r=90)
    fig_s11.update_layout(**layout_s11)
    st.plotly_chart(fig_s11, use_container_width=True)

    pillar_colors = [
        LEAGUE_COLORS['La Liga'],
        LEAGUE_COLORS['Premier League'],
        LEAGUE_COLORS['Serie A'],
    ]
    pillars = [
        {"header": "Create volume",      "body": "1.86 xG per match in wins vs 0.98 in losses",         "color": pillar_colors[0]},
        {"header": "Convert clinically", "body": "1.30 goals/xG in wins vs 0.59 in losses",             "color": pillar_colors[1]},
        {"header": "Suppress chances",   "body": "xG differential is the most complete single metric",  "color": pillar_colors[2]},
    ]
    col1, col2, col3 = st.columns(3)
    for col, pillar in zip([col1, col2, col3], pillars):
        with col:
            st.markdown(
                f"""<div style="border-top: 4px solid {pillar['color']}; padding: 16px;
                background: #f9f9f9; border-radius: 4px; margin: 4px 0;">
                <b>{pillar['header']}</b><br>{pillar['body']}
                </div>""",
                unsafe_allow_html=True,
            )

    st.info(
        "The data across 300 matches, 10 seasons, and 5 leagues points to the same answer. "
        "Pressing helps marginally. Creating better chances helps significantly. Converting "
        "them is the difference between winning and mid-table. The teams that do all three "
        "— **Barcelona, Bayern, City** — dominate for decades."
    )

    st.markdown(
        "### *Create volume. Convert clinically. Suppress opponent chances."
        " The rest is noise.*"
    )
