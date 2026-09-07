# integration-tests.md
- Ingestion e2e (moto Kinesis+S3): test_ingestion_e2e_moto (2) — producer→stream→consumer→S3,
  P0-01 checkpoint after durable write, duplicate retained at Bronze.
- Silver/Gold (local Spark): test_silver_gold_local_spark (6) — dedup, config flatten, DQ8/9/10, Gold agg.
- Failure/recovery (moto): test_failure_recovery (5) — DLQ routing, transient-failure retry, restart recovery, DLQ replay.
All PASS. Live Databricks pipeline run: NOT EXECUTED (needs workspace).
