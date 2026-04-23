import streamlit as st


def render():
    st.title("Technology Decisions")

    decisions = [
        (
            "Python 3.13 + soccerdata",
            "Manual scraping with `requests` + BeautifulSoup would require maintaining "
            "CSS selectors and session handling for each site. `soccerdata` abstracts "
            "that entirely — when Understat changes its HTML structure, the library "
            "update fixes all leagues at once, not just the one we happened to test.",
        ),
        (
            "GCS + BigQuery",
            "Local PostgreSQL was the original plan but fails at the boundaries: no "
            "partitioning, no columnar storage, and no separation between raw and "
            "transformed data. GCS provides cheap, durable bronze storage. BigQuery's "
            "partitioned columnar tables reduce bytes scanned per query by ~90% when "
            "filtering on `season`, which is critical for staying within the free tier.",
        ),
        (
            "dbt Core",
            "Python transformation scripts would mix business logic with I/O, making "
            "testing hard and lineage invisible. dbt gives us SQL models with "
            "built-in lineage, a test framework, and `ref()` that prevents stale "
            "intermediate tables. Every transformation is a versioned, testable SQL "
            "file — not a script that runs differently depending on environment state.",
        ),
        (
            "Parquet in GCS",
            "CSV doubles storage size for this dataset and loses column type "
            "information — every load would need manual schema inference. Parquet "
            "stores schema inline, compresses ~4× better, and BigQuery can load it "
            "without a schema file. For 521,148 player stat rows this saves ~200 MB "
            "of GCS storage.",
        ),
        (
            "Streamlit (presentation layer)",
            "Streamlit queries BigQuery mart tables directly with a dry-run cost guard "
            "and one-hour result caching. This removes the need for a separate serving "
            "database — the dbt marts are already the right granularity for the app, "
            "and cached results keep repeat BigQuery scans near zero during a session.",
        ),
        (
            "GitHub Actions",
            "Airflow and Prefect are the right tools for pipelines with complex "
            "dependencies, retries, and SLA monitoring. This pipeline runs once per "
            "season update (manually triggered), has five sequential steps, and lives "
            "in a single repo. GitHub Actions is already present, requires no "
            "infrastructure to run, and a `workflow_dispatch` trigger is exactly the "
            "right abstraction for an on-demand pipeline.",
        ),
        (
            "StatsBomb Open Data",
            "FBref is the obvious choice for pressing and carry metrics but it hard-blocks "
            "scrapers with HTTP 403 at the league index level — not a rate-limit, a policy "
            "block. StatsBomb publishes structured open data via `statsbombpy` with no "
            "scraping required. The coverage gap (select seasons only) is an acceptable "
            "tradeoff; Understat's PPDA and deep completions cover the pressing signal "
            "for all 10 seasons.",
        ),
    ]

    for choice, reason in decisions:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{choice}**")
        with col2:
            st.markdown(reason)
        st.markdown("---")

    st.markdown("### Code Patterns")

    st.markdown("**GCS blob path convention**")
    st.code(
        'bronze/{league}/{source}/{season}/{table}.parquet\n'
        '# e.g.\n'
        'bronze/bundesliga/understat/2024/player_stats.parquet',
        language="text",
    )

    st.markdown("**BigQuery dry-run safety check (applied before every query)**")
    st.code(
        """from google.cloud import bigquery
from pipeline.config import GCP_PROJECT_ID

client = bigquery.Client(project=GCP_PROJECT_ID)

job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
job = client.query(sql, job_config=job_config)
estimated_gb = job.total_bytes_processed / 1e9

if estimated_gb > 10:
    raise RuntimeError(f"Query scans {estimated_gb:.2f} GB — exceeds 10 GB limit")
""",
        language="python",
    )

    st.markdown("### Deliberately Ruled Out")
    ruled_out = {
        "FBref": "Hard-blocked at 403 — actively detects and rejects scraper user-agents at the league index endpoint. Not a rate-limit. No known workaround.",
        "Club Elo API": "`ClubElo` object has no `.read_by_club()` method. Correct method name needs verification via `dir(sd.ClubElo())` before any code is written.",
        "ORM layers (SQLAlchemy)": "No benefit here — all queries are analytical SQL against BigQuery and Supabase. An ORM adds mapping overhead with no type safety gain over raw SQL.",
        "FotMob via soccerdata": "API integration does not work reliably. Blocked.",
        "Airflow / Prefect": "No infrastructure budget. GitHub Actions covers the use case with zero overhead.",
    }
    for tool, reason in ruled_out.items():
        st.markdown(f"**{tool}** — {reason}")
