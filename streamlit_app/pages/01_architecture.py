import streamlit as st


def render():
    st.title("System Architecture")

    st.graphviz_chart(
        """
        digraph pipeline {
            rankdir=LR;
            node [shape=box style=filled fontname="Helvetica" fontsize=11];

            subgraph cluster_sources {
                label="Data Sources";
                style=dashed;
                Understat [fillcolor="#AED6F1"];
                ESPN      [fillcolor="#AED6F1"];
                StatsBomb [fillcolor="#AED6F1"];
            }

            subgraph cluster_gcp {
                label="GCP";
                style=dashed;
                GCS       [label="GCS Bronze\\n(Parquet)" fillcolor="#A9DFBF"];
                BQ_raw    [label="BigQuery Raw"           fillcolor="#A9DFBF"];
                BQ_stg    [label="dbt Staging"            fillcolor="#FAD7A0"];
                BQ_int    [label="dbt Intermediate"       fillcolor="#FAD7A0"];
                BQ_marts  [label="dbt Marts"              fillcolor="#FAD7A0"];
            }

            Supabase  [label="Supabase\\n(REST API)" fillcolor="#D7BDE2"];
            Lovable   [label="Lovable\\nFrontend"    fillcolor="#FADBD8"];

            Understat -> GCS;
            ESPN      -> GCS;
            StatsBomb -> GCS;
            GCS       -> BQ_raw;
            BQ_raw    -> BQ_stg;
            BQ_stg    -> BQ_int;
            BQ_int    -> BQ_marts;
            BQ_marts  -> Supabase;
            Supabase  -> Lovable;
        }
        """
    )

    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Ingestion")
        st.markdown(
            """
            `soccerdata` scrapes Understat and ESPN in parallel using
            `ThreadPoolExecutor(max_workers=5)`. Data is serialised to Parquet
            in-memory and uploaded to GCS under `bronze/{league}/{source}/{season}/`.
            Incremental by default — files already in GCS are skipped.
            """
        )

    with col2:
        st.markdown("#### Transformation")
        st.markdown(
            """
            dbt Core runs three model layers against BigQuery. Staging cleans and
            types raw data. Intermediate computes team-level aggregates per match.
            Marts pre-aggregate to league × season × result combinations ready for
            direct frontend consumption. All models are partitioned by `season`.
            """
        )

    with col3:
        st.markdown("#### Serving")
        st.markdown(
            """
            Mart results are pushed to Supabase once after each pipeline run.
            The Lovable frontend reads exclusively from Supabase — it never
            queries BigQuery. This decouples query cost from frontend traffic
            and keeps GCP free-tier usage bounded.
            """
        )

    st.markdown("---")
    st.markdown("### Schema Philosophy")
    st.markdown(
        """
        The schema has exactly **three tables**: `matches`, `player_stats`, and `lineups`.

        `league` and `season` are always **columns**, never table names or schema names.
        Cross-league analysis is a `WHERE league IN (...)` clause — not a UNION across
        five separate tables. This matters because:

        - A single index on `(league, season)` satisfies every analytical query.
        - dbt models reference one source table, not five, so there is no per-league
          duplication of transformation logic.
        - Adding a sixth league (or removing one) requires no schema migration — only
          a new row in the scraper config.

        BigQuery datasets map to dbt layers: `raw` → `staging` → `intermediate` → `marts`.
        No data ever moves between datasets except by a dbt model run. There are no
        ad-hoc INSERT or UPDATE statements anywhere in the pipeline.
        """
    )
