##############################################################################
# Athena module — Glue catalog, telemetry table, workgroup, results bucket
##############################################################################

data "aws_caller_identity" "current" {}

locals {
  account_id     = data.aws_caller_identity.current.account_id
  results_bucket = "${var.name_prefix}-athena-results-${local.account_id}"
}

# ── Results bucket ──────────────────────────────────────────────────────────
resource "aws_s3_bucket" "athena_results" {
  bucket        = local.results_bucket
  force_destroy = true
  tags          = merge(var.tags, { Name = local.results_bucket })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    id     = "expire-results"
    status = "Enabled"
    filter { prefix = "" }
    expiration { days = 7 }
  }
}

# ── Dashboard cache prefix inside lake bucket ────────────────────────────────
# (Lambda writes processed/dashboard_cache.json to the lake bucket)

# ── Athena workgroup ─────────────────────────────────────────────────────────
resource "aws_athena_workgroup" "fleet" {
  name          = "${var.name_prefix}-fleet"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-fleet-workgroup" })
}

# ── Glue database ────────────────────────────────────────────────────────────
resource "aws_glue_catalog_database" "fleet" {
  name        = replace("${var.name_prefix}_fleet", "-", "_")
  description = "IAP fleet telemetry data lake catalog"
}

# ── Glue table — raw telemetry (JSONL, Hive-partitioned) ─────────────────────
resource "aws_glue_catalog_table" "telemetry" {
  name          = "telemetry"
  database_name = aws_glue_catalog_database.fleet.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification"        = "json"
    "compressionType"       = "none"
    "EXTERNAL"              = "TRUE"
    "projection.enabled"    = "false"
  }

  storage_descriptor {
    location      = "s3://${var.lake_bucket}/raw/telemetry/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "json-serde"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "serialization.format" = "1"
        "ignore.malformed.json" = "true"
      }
    }

    # Top-level scalar columns
    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "timestamp"
      type = "string"
    }
    columns {
      name = "vehicle_id"
      type = "string"
    }
    columns {
      name = "driver_id"
      type = "string"
    }
    columns {
      name = "driver_name"
      type = "string"
    }
    columns {
      name = "speed_kmh"
      type = "double"
    }
    columns {
      name = "heading_deg"
      type = "double"
    }
    columns {
      name = "odometer_km"
      type = "double"
    }
    columns {
      name = "geofence"
      type = "string"
    }
    columns {
      name = "trip_id"
      type = "string"
    }
    columns {
      name = "schema_version"
      type = "string"
    }
    columns {
      name = "source"
      type = "string"
    }

    # Nested structs
    columns {
      name = "vehicle_info"
      type = "struct<make:string,model:string,year:int,type:string,plate:string,vin:string>"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lng:double,altitude:double,accuracy:double>"
    }
    columns {
      name = "engine"
      type = "struct<rpm:double,temperature_c:double,oil_pressure_kpa:double,coolant_temp_c:double,throttle_pct:double,battery_soc_pct:double,motor_temp_c:double,regen_braking_kw:double,power_draw_kw:double>"
    }
    columns {
      name = "fuel"
      type = "struct<level_pct:double,consumption_per_100km:double,type:string,kwh_consumed:double>"
    }
    columns {
      name = "driver_behavior"
      type = "struct<harsh_braking:boolean,harsh_acceleration:boolean,speeding:boolean,idle_time_s:double,safety_score:double,seatbelt_on:boolean,phone_usage:boolean>"
    }
    columns {
      name = "predictive_maintenance"
      type = "struct<brake_health:double,tire_health:double,oil_change_due_km:double,filter_due_km:double,next_service_days:int,overall_health_score:double>"
    }
    columns {
      name = "fault_codes"
      type = "array<struct<code:string,description:string,severity:string,first_seen:string>>"
    }
    columns {
      name = "network"
      type = "struct<signal_strength:double,protocol:string>"
    }
  }

  # Hive partition keys
  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
}
