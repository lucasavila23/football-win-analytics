import streamlit as st
import pandas as pd


def render():
    st.title("Data Pipeline")

    with st.expander("1. Scraping", expanded=False):
        st.markdown(
            """
            All scraping uses the [`soccerdata`](https://soccerdata.readthedocs.io) library.
            No direct HTTP requests, no Selenium — `soccerdata` handles session management,
            rate limiting, and HTML parsing for both Understat and ESPN.

            **Parallelism:** leagues are scraped concurrently using
            `ThreadPoolExecutor(max_workers=5)`. Each thread runs one full
            `(league, season)` combination. Timeout is **600 seconds per league** —
            set high because Understat's player stats endpoint is slow under shared
            network contention.

            **Closure pattern to avoid loop variable capture bugs:**
            ```python
            tasks = [(lambda lid: lambda: scrape(lid))(league_id) for league_id in leagues]
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(t) for t in tasks]
            ```

            **Validated match rates** (season 2023, all leagues):

            | League | Understat matches | ESPN lineups | Join rate |
            |---|---|---|---|
            | La Liga | 380 | 380 | ~100% |
            | Premier League | 380 | 380 | ~100% |
            | Bundesliga | 306 | 306 | 100% (after normalisation) |
            | Serie A | 380 | 380 | ~100% |
            | Ligue 1 | 306 | 306 | ~100% |
            """
        )

    with st.expander("2. GCS Upload", expanded=False):
        st.markdown(
            """
            Scraped DataFrames are serialised to Parquet in memory (via `BytesIO`) and
            uploaded to GCS using `google-cloud-storage`. No temporary local files.

            **Blob path convention (immutable):**
            ```
            bronze/{league}/{source}/{season}/{table}.parquet
            ```
            Example: `bronze/bundesliga/understat/2024/player_stats.parquet`

            **Idempotency:** `overwrite=False` is the production default. The loader
            calls `list_blobs(league, source, season)` first and skips any file that
            already exists in GCS. Use `overwrite=True` only for explicit reruns.

            **Batch constraint:** uploads are never issued row-by-row or per-match.
            The minimum upload unit is one full league + season. This is enforced by
            `upload_multiple()` in `pipeline/loaders/gcs_loader.py`.
            """
        )

    with st.expander("3. BigQuery Load", expanded=False):
        st.markdown(
            """
            GCS Parquet files are loaded into BigQuery's `raw` dataset using the
            BigQuery Storage Write API via `google-cloud-bigquery`.

            - **Load mode:** `WRITE_APPEND` — new rows are appended; existing rows are
              never deleted or overwritten during normal runs.
            - **Table naming:** `{source}_{table}` e.g. `understat_matches`,
              `espn_lineups`.
            - **Dry-run safety:** every query (including load job previews) runs a
              dry-run first. If estimated bytes exceed 10 GB the job is aborted.
            - **Partition column:** `season` (STRING). All downstream queries filter on
              `season` to reduce bytes scanned.

            All three tables (`matches`, `player_stats`, `lineups`) have schema files
            in `pipeline/loaders/schemas/` — BigQuery validates column types on every
            load.
            """
        )

    with st.expander("4. dbt Transformation", expanded=False):
        st.markdown(
            """
            dbt Core runs three model layers, each building on the previous.

            | Layer | Model prefix | What it does |
            |---|---|---|
            | Staging | `stg_*` | Clean, type-cast, standardise. One model per source table. |
            | Intermediate | `int_*` | Join Understat + ESPN on Date + Normalised Team. Compute per-match aggregates. |
            | Marts | `mart_*` | Pre-aggregate to app-ready granularity. Written to Supabase. |

            **Hard rules:**
            - Never `SELECT *` on any non-trivial table — all columns listed explicitly.
            - Every model filters on `season` — BigQuery partition pruning reduces
              bytes scanned by ~90% for single-season queries.
            - `SAFE_DIVIDE` everywhere — no division-by-zero crashes in production.
            - Singular tests: `assert_no_negative_xg`, `assert_match_has_two_teams`.

            Full dbt DAG: **PASS=12 models, PASS=18 tests** on dataset covering
            18,085 matches.
            """
        )

    with st.expander("5. Supabase Sync", expanded=False):
        st.markdown(
            """
            After each successful dbt run, `pipeline/loaders/supabase_loader.py`
            reads mart tables from BigQuery and upserts them into Supabase via the
            Supabase Python client.

            - **Upsert, not insert** — re-running the sync is safe.
            - **App never queries BigQuery directly** — Supabase is the only serving
              layer. This means query cost is bounded to pipeline runs, not user traffic.
            - Supabase DDL is in `docs/supabase_schema.sql`.
            """
        )

    st.warning(
        "**Known limitations:**\n"
        "- ESPN historical data returns 500 errors for seasons before 2016/2017 — "
        "unfixable at source. Understat covers the full 10 seasons independently.\n"
        "- StatsBomb progressive carries are **not** loaded into the mart — open data "
        "only covers select seasons per league (~70% NULL rows in mart_winning_profiles "
        "if included). Understat xG signals are sufficient.\n"
        "- FBref is **hard-blocked** (HTTP 403 at league index endpoint). "
        "Do not attempt to scrape FBref."
    )

    st.markdown("---")
    st.markdown("### Team Name Normalisation — The Bundesliga Problem")
    st.markdown(
        """
        Understat and ESPN use different team name formats. A naive join on raw team
        names produces catastrophically low match rates for some leagues.
        `normalize_name()` in `pipeline/utils.py` strips accents, lowercases, removes
        punctuation, and applies a league-specific alias table.
        """
    )

    norm_data = {
        "League": ["La Liga", "Premier League", "Bundesliga", "Serie A", "Ligue 1"],
        "Raw match rate": ["~95%", "~98%", "38.9%", "~92%", "~94%"],
        "After normalisation": ["100%", "100%", "100%", "100%", "100%"],
    }
    st.table(pd.DataFrame(norm_data))

    st.markdown(
        """
        Bundesliga is the critical case — 38.9% raw match rate — because German team
        names differ most between sources (e.g. `"Bayern Munich"` vs `"FC Bayern München"`).
        Every join between Understat and ESPN **must** go through `normalize_name()`.
        """
    )
