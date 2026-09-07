# Databricks notebook source
import dlt
from pyspark.sql.functions import *

# BUGFIX: previously hardcoded the ADLS source path here, ignoring the
# `bronze_path` value already defined in the pipeline's `configuration:`
# block (databricks/resources/pipelines/dlt.yml). That meant the dev
# storage account/path was baked into the notebook itself, so the same
# code could not be pointed at a different environment (test/prod)
# without editing Python. Now reads the path from pipeline configuration,
# matching how bronze_path is already declared for this pipeline.
bronze_path = spark.conf.get("bronze_path")

@dlt.table(
    name="telemetry_bronze",
    comment="Raw telemetry ingested from ADLS Gen2 using Auto Loader"
)
def telemetry_bronze():
    # BUGFIX: dlt/silver/clean_and_deduplicate.py selects _source_file and
    # _ingested_at (the latter also used to pick the most-recent record
    # per event_id during deduplication), but this table never produced
    # either column, causing
    # `UNRESOLVED_COLUMN.WITH_SUGGESTION: ... _source_file ...` at
    # pipeline-run time. input_file_name() (the usual batch fix) does not
    # work here because this is a streaming Auto Loader source; the
    # equivalent for streaming file sources is Databricks' built-in
    # `_metadata` column, available on any file-based source including
    # cloudFiles.
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(bronze_path)
        .withColumn("_source_file", col("_metadata.file_path"))
        .withColumn("_ingested_at", col("_metadata.file_modification_time"))
    )
