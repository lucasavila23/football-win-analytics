from google.cloud import bigquery
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()

client = bigquery.Client(project=os.getenv("GCP_PROJECT_ID"))

# Check what tables exist in the raw dataset
tables = list(client.list_tables("raw"))
for t in tables:
    print(t.table_id)

# Query a table (once data exists)
query = """
    SELECT * FROM `raw.understat_matches`
    WHERE league = 'la_liga' AND season = '2023'
    LIMIT 100
"""
df = client.query(query).to_dataframe()
print(df.head())