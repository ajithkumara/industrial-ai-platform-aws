# bronze-evidence.md
- Bronze immutability + raw retention proven at the ingestion boundary:
  test_ingestion_e2e_moto shows duplicate events BOTH written to S3 raw/ (DQ2 Bronze=2).
- Bronze Auto Loader notebook (dlt/bronze/ingest_raw_events.py) is byte-identical to Azure;
  only bronze_path (s3://) differs, set in the DAB pipeline config.
- Live Auto Loader ingest into industrial_ai.bronze.telemetry_bronze: NOT EXECUTED (needs Databricks).
