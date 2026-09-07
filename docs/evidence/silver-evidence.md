# silver-evidence.md — Milestone 7 (Silver, local Spark reproduction)

- **Date (UTC):** 2026-09-07
- **Engine:** local PySpark 3.5.3 on Java 11 (SPARK_LOCAL_IP=127.0.0.1)
- **Command:** `python3 -m pytest tests/spark/test_silver_gold_local_spark.py -v`
- **Result:** **6 passed.**

## Code parity (the DLT notebooks themselves)

`dlt/silver/clean_and_deduplicate.py` and `dlt/silver/flatten_payloads.py` are
**byte-identical** to the Azure reference (verified by diff — see M7 parity
check; 11/11 DLT notebooks identical). The only cloud difference in the whole
pipeline is the DAB `bronze_path` (s3:// vs abfss://) and the removal of the
Azure ABFS OAuth spark config — both in `databricks/resources/pipelines/dlt.yml`,
never in a notebook.

## Logical reproduction (real Spark, real configs)

The test reads synthetic events as JSON (mirroring the Bronze Auto Loader's
schema inference), then applies the SAME Silver operations the notebook does
(select + `to_timestamp` + the 4 `expect_or_drop` identity filters with
`TRIM<>''` + dedup by event_id keeping latest `_ingested_at`), and the SAME
config-driven flatten using the real `config/asset_types/*.yml` +
`dlt/common/helpers.py`.

| Test | Acceptance contract | Result |
|---|---|---|
| test_dq2_duplicate_bronze2_silver1 | DQ2: Bronze 2 → Silver 1 (dedup) | PASS |
| test_dq7_unparseable_timestamp_dropped_at_silver | DQ7: bad timestamp dropped at Silver | PASS |
| test_dq8_unknown_asset_retained_but_not_flattened | DQ8: unknown asset retained in cleaned, no flattened table | PASS |
| test_dq9_missing_payload_field_becomes_null_column | DQ9: missing `payload.features.rms` → `rms` NULL column | PASS |
| test_dq10_wrong_payload_type_becomes_null_column | DQ10: uncastable `kurtosis` → NULL (not error) | PASS |

These reproduce the Azure acceptance values UNCHANGED (not weakened).

## NOT EXECUTED

The DLT-decorated notebooks run only inside a Databricks DLT pipeline
(`import dlt`). `databricks bundle validate/deploy` and a live pipeline run are
NOT EXECUTED (Databricks CLI network-blocked here; needs a workspace). Commands:
`databricks bundle validate -t dev` then `databricks bundle deploy -t dev`.
The local Spark test above verifies the transformation LOGIC; the notebook code
is proven identical to the already-accepted Azure implementation.
