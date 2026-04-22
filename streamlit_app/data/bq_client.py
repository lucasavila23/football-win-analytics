import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from pipeline.config import GCP_PROJECT_ID

_BYTES_LIMIT = 10 * 1_000_000_000  # 10 GB


def _get_client() -> bigquery.Client:
    return bigquery.Client(project=GCP_PROJECT_ID)


@st.cache_data(ttl=3600)
def run_query(sql: str) -> pd.DataFrame:
    client = _get_client()

    dry_run_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_run_job = client.query(sql, job_config=dry_run_config)
    estimated = dry_run_job.total_bytes_processed
    if estimated > _BYTES_LIMIT:
        raise RuntimeError(
            f"Query would scan {estimated / 1e9:.2f} GB — exceeds 10 GB safety limit. "
            "Aborting to protect GCP free tier."
        )

    job = client.query(sql)
    return job.result().to_dataframe()
