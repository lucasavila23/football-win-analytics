import streamlit as st


def render():
    st.title("Football Analytics Platform")
    st.subheader("Characteristics of Winning Teams Across Europe's Top 5 Leagues")

    st.markdown(
        """
        This platform investigates what separates winning teams from drawing or losing
        teams across La Liga, Premier League, Bundesliga, Serie A, and Ligue 1 over ten
        seasons (2014–2023). By combining expected goals (xG) from Understat with lineup
        and event data from ESPN, it moves beyond goals and points to ask: do winning
        teams create higher-quality chances, press more intensely, or penetrate deeper
        into dangerous areas — and does the answer hold consistently across leagues?
        """
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matches ingested", "18,085")
    c2.metric("Player stat rows", "521,148")
    c3.metric("Leagues covered", "5")
    c4.metric("Seasons", "10 (2014–2023)")

    st.info(
        "**Data sources:** "
        "[Understat](https://understat.com) — xG, PPDA, deep completions, np_xG per match · "
        "[ESPN](https://www.espn.com) — lineups, player events, formations · "
        "[StatsBomb Open Data](https://github.com/statsbomb/open-data) — progressive carries "
        "(select seasons only)"
    )

    st.markdown("### What this platform does")
    st.markdown(
        """
        - **Ingests** match and player data from two sources via `soccerdata`, stores
          Parquet files in GCS, and loads them into BigQuery with strict idempotency
          guarantees.
        - **Transforms** raw data through a three-layer dbt pipeline (staging → intermediate
          → marts) to produce pre-aggregated, analytics-ready tables partitioned by season
          and league.
        - **Serves** results directly in this Streamlit app, which queries BigQuery mart
          tables with dry-run cost guards and one-hour caching — keeping typical query
          costs near zero for exploratory use.
        """
    )
