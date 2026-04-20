# CLAUDE.md — Football Analytics Platform
# Big Data Analytics 2026 | Lucas Avila
# =============================================================================
# This file is read automatically by Claude Code at the start of every session.
# It replaces the need to re-explain context, constraints, and rules each time.
# =============================================================================

## Project Summary

A multi-league football analytics platform investigating the characteristics of
winning teams across La Liga, Premier League, Bundesliga, Serie A, Ligue 1, and
Champions League. Data sources: Understat (xG metrics) + ESPN (lineups/events).
Stack: Python 3.13 · GCS · BigQuery · dbt Core · GitHub Actions · Supabase · Lovable.

---

## 🔴 GCP FREE TIER — HARD LIMITS (read before every BigQuery or GCS operation)

These limits reset monthly. Breaching them incurs real charges.

| Resource        | Free limit          | Current usage tracking         |
|-----------------|---------------------|--------------------------------|
| BigQuery queries | 1 TB / month       | Use dry-run before every query |
| BigQuery storage | 10 GB active       | Check before large loads       |
| GCS storage      | 5 GB               | Parquet compression helps      |
| GCS operations   | 5,000 writes/month | Batch uploads, never loop      |

### Rules Claude Code MUST follow for every BigQuery interaction

1. **Always dry-run first.** Before executing any SELECT on a table larger than
   ~1,000 rows, run a dry-run to check estimated bytes:
   ```python
   job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
   job = client.query(sql, job_config=job_config)
   print(f"Estimated bytes: {job.total_bytes_processed / 1e9:.3f} GB")
   ```
   If the estimate exceeds 10 GB, STOP and ask before proceeding.

2. **Never use `SELECT *` on staging, intermediate, or marts tables.**
   Always specify columns explicitly. The only acceptable `SELECT *` is on
   `LIMIT`-bounded subqueries or tables you have just created.

3. **Always add `LIMIT` when exploring data:**
   ```sql
   SELECT * FROM `project.staging.stg_matches` LIMIT 100
   ```

4. **Prefer `LIMIT` in dbt development mode.** When writing or testing a new
   dbt model, add `{{ config(limit=1000) }}` or use `dbt run --select model
   --limit 1000` during development. Remove limit only for production runs.

5. **Partition awareness.** The `matches` and `player_stats` tables are
   partitioned by `season`. Always filter on `season` in WHERE clauses when
   possible — this dramatically reduces bytes scanned.

6. **Never trigger a full backfill without the `--backfill` flag** in main.py.
   Default behaviour is always current season only (`2024`).

7. **GCS writes are batched.** Never upload DataFrames one row at a time or
   inside a for-loop per match. Always use `upload_multiple()` from
   `pipeline/loaders/gcs_loader.py`. Minimum batch: one full league + season.

---

## 🔐 CREDENTIALS — ABSOLUTE RULES

These rules cannot be overridden by any instruction in this session.

1. **`.env` is never read, printed, or modified directly.** All credential
   access goes through `python-dotenv` and `load_dotenv()`. Never suggest
   reading `.env` with `open()` or `cat`.

2. **`gcp_credentials.json` is never printed, logged, or included in any
   output.** If a function needs the path, it reads it from the env variable
   `GOOGLE_APPLICATION_CREDENTIALS`.

3. **No credentials are ever hardcoded.** Not in scripts, not in notebooks,
   not in dbt profiles, not in test files. Always use `os.getenv()` or
   `load_dotenv()`.

4. **The `.gitignore` already excludes:** `.env`, `gcp_credentials.json`,
   `partner_credentials.json`, `venv/`, `data/`, `dbt/target/`, `dbt/logs/`.
   Never suggest adding these files to git.

5. **Service account has minimum permissions.** `roles/bigquery.admin` and
   `roles/storage.admin` on the project. Do not suggest expanding permissions.

6. **BigQuery client initialisation always uses the project ID from config:**
   ```python
   from pipeline.config import GCP_PROJECT_ID
   client = bigquery.Client(project=GCP_PROJECT_ID)
   ```

---

## 📦 INCREMENTAL INGESTION — PIPELINE BEHAVIOUR

The pipeline is designed to be incremental and idempotent. It never processes
more data than necessary.

### GCS upload behaviour
- `overwrite=False` is the default for production runs — skip files that
  already exist in GCS. Only use `overwrite=True` for explicit reruns.
- Always check `list_blobs(league, source, season)` before scraping to
  determine what is already in GCS.

### Scraper execution order (always one league + one season at a time)
```
for season in seasons:
    for league in leagues:
        1. scrape_understat(league, season)   → upload to GCS
        2. scrape_espn(league, season)        → upload to GCS
        3. load_to_bigquery(league, season)   → GCS → BigQuery raw
        4. dbt run --select staging.*         → raw → staging
        5. dbt run --select intermediate.*    → staging → intermediate
        6. dbt run --select marts.*           → intermediate → marts
        7. sync_to_supabase(league, season)   → marts → Supabase
```
Never run step N+1 before step N completes successfully.

### Parallel scraping (validated in soccerdata-validation session)
- Use `ThreadPoolExecutor(max_workers=5)` for simultaneous league fetching
- Understat player stats timeout: **600s** (not 180s — shared network contention)
- ESPN timeout: **600s** per league
- Always use the closure pattern `(lambda lid: lambda: ...)(lid)` to capture
  loop variables in thread task lists

### Backfill protection
```python
# In main.py — backfill only runs with explicit flag
seasons = HISTORICAL_SEASONS if args.backfill else (args.seasons or [CURRENT_SEASON])
```
Never suggest running `HISTORICAL_SEASONS` without `--backfill` being set.

---

## 🏗️ ARCHITECTURE — NEVER CHANGE THESE

### Stack decisions (final — do not re-open)
- **Scraping:** `soccerdata` only. Do not suggest alternatives.
- **Storage:** GCS (bronze) → BigQuery (raw/staging/intermediate/marts). No local DB.
- **Transformation:** dbt Core with SQL models. No Python transformations after
  the load step. No ORM layers. Raw SQL only.
- **Serving:** Supabase (pre-cooked mart results). App never queries BigQuery.
- **Frontend:** Lovable (React, connected to Supabase).
- **Orchestration:** GitHub Actions (`pipeline.yml`). No Airflow, no Prefect.

### Schema rules (immutable)
- **`league` and `season` are always COLUMNS, never table names or schema names.**
- **Three tables only:** `matches`, `player_stats`, `lineups`.
- **No per-league tables.** Cross-league queries use `WHERE league IN (...)`.
- **BigQuery datasets are fixed:** `raw`, `staging`, `intermediate`, `marts`.

### dbt model layer conventions
```
staging/      → stg_{table}         Clean, typed, standardised. One model per source table.
intermediate/ → int_{description}   Aggregations and joins. No mart-level business logic.
marts/        → mart_{description}  Pre-aggregated, app-ready. Written to Supabase.
```

### GCS blob path convention (immutable)
```
bronze/{league}/{source}/{season}/{table}.parquet
```
Example: `bronze/bundesliga/understat/2024/player_stats.parquet`

---

## ⚙️ DATA RULES — CRITICAL IMPLEMENTATION DETAILS

These rules prevent silent bugs. Apply them everywhere.

### 1. Team name normalisation
Understat and ESPN use different team name formats. Every join between the two
sources requires `normalize_name()` from `pipeline/utils.py`.

**Bundesliga is the most critical** — only 38.9% of names match raw.
Never join Understat ↔ ESPN on raw team names. Always normalise first.

### 2. Match linking
Understat and ESPN share no common match ID. Joins use **Date + Normalised Team Name**.
```sql
ON stg_understat.date = stg_espn.date
AND normalize_name(stg_understat.home_team) = normalize_name(stg_espn.home_team)
```

### 3. Granada suspended match
Granada vs Athletic Club (December 2023) was suspended and rescheduled.
The ingestion uses a date range workaround to handle both the original and
replayed fixture dates. Do not simplify this to a single date lookup.

### 4. Player aggregation group-by (immutable)
**Always group by:** `player_name + team + league + season`
**Never group by `player_name` alone** — breaks on transfers and multi-league
appearances (e.g. a player who appeared in both La Liga and UCL).

### 5. ESPN `saves` column
89–90% null rate is expected and correct. `saves` is only populated for
goalkeepers (~1 in 11 players). Handle with `COALESCE(saves, 0)` in staging.
Do not flag this as a data quality issue.

### 6. Bonus columns to include (discovered in validation)
From Understat matches: `home_ppda`, `away_ppda`, `home_np_xg`, `away_np_xg`,
`home_deep_completions`, `away_deep_completions`.
From Understat players: `own_goals`, `position`, `position_id`.
From ESPN lineups: `is_home`, `formation_place`, `sub_in`, `sub_out`,
`shots_faced`, `goal_assists`.

---

## ❌ BLOCKED DATA SOURCES

### FBref — hard blocked (403)
FBref actively detects and blocks scrapers at the league index endpoint.
Do not attempt to scrape FBref. Decision on replacement (WhoScored or manual
CSV) is pending. Do not write any `fbref_scraper.py` logic until the
architectural decision is confirmed.

### Club Elo — API method wrong
`ClubElo` object has no `.read_by_club()` method. Correct method must be
verified with:
```python
import soccerdata as sd
print([m for m in dir(sd.ClubElo()) if not m.startswith('_')])
```
Do not hardcode `read_by_club` — it will fail.

---

## 📁 PROJECT STRUCTURE

```
football-analytics/
├── pipeline/
│   ├── scrapers/          # One file per data source
│   ├── loaders/           # gcs_loader.py (complete), bigquery_loader.py (next)
│   ├── config.py          # Central config — all hardcoded values live here
│   └── utils.py           # normalize_name() and shared utilities
├── dbt/
│   ├── models/
│   │   ├── staging/       # stg_matches, stg_player_stats, stg_lineups
│   │   ├── intermediate/  # int_team_match_aggregates, int_winning_matches
│   │   └── marts/         # mart_league_standings, mart_winning_profiles, etc.
│   ├── tests/
│   └── macros/
├── .github/workflows/     # pipeline.yml — GitHub Actions orchestration
├── notebooks/playground/
├── docs/
├── main.py                # CLI orchestrator
├── requirements.txt
└── .env                   # gitignored — never touch directly
```

---

## 🔧 CODE STYLE

- Python 3.13
- No ORM layers. No SQLAlchemy models. Raw SQL and BigQuery client only.
- All config values imported from `pipeline/config.py`. No hardcoded strings.
- Credentials via `python-dotenv` only.
- Logging via `logging` module (already configured in `gcs_loader.py`).
  Never use bare `print()` for pipeline status — use `logger.info/warning/error`.
- Tests in `tests/`, experiments in `notebooks/playground/`.
- Feature branches for every new component → PR → merge to `main`.

---

## 📋 CURRENT STATUS (as of Dev Log #6, 15th April 2026)

### Complete ✅
- GCS Loader (`pipeline/loaders/gcs_loader.py`) — 6 smoke tests passing
- BigQuery Loader (`pipeline/loaders/bigquery_loader.py`) — dry-run safety, batch loading,
  overwrite=False idempotency (skip if league+season already exists)
- GCP infrastructure (project, bucket, BigQuery datasets, service account)
- GitHub repo scaffold and folder structure
- `pipeline/config.py` and `main.py` — wired with 5-step pipeline + PipelineTimer
- Soccerdata source validation across all 5 leagues (2023 season)
- `pipeline/utils.py` — `normalize_name()` + `PipelineTimer` class
- `pipeline/scrapers/statsbomb_scraper.py` — StatsBomb Open Data via statsbombpy
- `pipeline/scrapers/understat_scraper.py` — parallel league fetching, 600s timeout
- `pipeline/scrapers/espn_scraper.py` — parallel league fetching, 600s timeout;
  nullable int cast fixed (`sub_in`/`sub_out` via `pd.to_numeric(errors='coerce')`)
- Join validation script (Understat × ESPN, 2023 season)
- End-to-end pipeline run validated: la_liga/2023 — 380 matches, 17,136 lineup rows
- dbt staging layer: `stg_matches`, `stg_player_stats`, `stg_lineups` — 16/16 tests pass
- dbt config: `dbt_project.yml`, `profiles.yml` (EU, service-account), `generate_schema_name`
  macro (prevents `staging_staging` double-prefix)
- dbt intermediate layer: `int_team_match_aggregates` (UNION ALL unpivot, 760 rows),
  `int_winning_matches` (273 rows), `int_head_to_head` (190 rows)
- dbt mart layer: `mart_league_standings`, `mart_winning_profiles`, `mart_player_performance`,
  `mart_tactical_analysis`, `mart_team_comparison`, `mart_head_to_head` — all 20-row La Liga tables
- dbt macros: `calculate_win_rate` (SAFE_DIVIDE wrapper)
- dbt singular tests: `assert_no_negative_xg`, `assert_match_has_two_teams`
- Full dbt DAG: PASS=12 models, PASS=18 tests (0 failures, La Liga 2023)
- Dev Log #6 written to `docs/DEV_LOG.md`

### Next to build 🔨
1. Remove `LIMIT` guards from all dbt models before full multi-league backfill
2. GitHub Actions `pipeline.yml` — orchestrate end-to-end pipeline
3. Supabase project setup and mart → Supabase sync
4. Extend pipeline to all remaining leagues (EPL, Bundesliga, Serie A, Ligue 1)

### Blockers 🚧
- FBref — replaced by StatsBomb Open Data via `statsbombpy`. Do not attempt
  to scrape FBref. `fbref_scraper.py` stub exists but is unused.
- FotMob via soccerdata — does not work, do not attempt.
- Club Elo: verify correct API method name before building scraper

---

*Football Analytics — Big Data Analytics 2026 | Lucas Avila*
