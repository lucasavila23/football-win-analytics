-- Override dbt's default schema name generation.
--
-- Default behaviour: combines profile dataset + custom schema, e.g.
--   profile dataset="staging" + model schema="staging" → "staging_staging"
--
-- This macro: uses the custom schema name as-is when provided.
--   profile dataset="staging" + model schema="staging" → "staging"
--   profile dataset="staging" + model schema="marts"   → "marts"
--
-- This means our models land in the exact BigQuery datasets defined in
-- CLAUDE.md (raw, staging, intermediate, marts) with no prefixing.

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
