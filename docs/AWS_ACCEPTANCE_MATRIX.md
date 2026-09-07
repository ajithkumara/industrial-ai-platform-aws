# AWS_ACCEPTANCE_MATRIX.md — Milestone 1 (acceptance), status as of M13

> The Azure acceptance criteria converted to AWS, with the AWS implementation,
> the test, and status. Expected values are UNCHANGED from Azure
> (see ACCEPTANCE_CONTRACT.md). Status: PASS (executed), PARTIAL (offline half
> executed, live half pending), NOT VERIFIED (needs live cluster).

| ID | Capability | Azure impl | AWS impl | Expected | Test | Evidence | Status |
|---|---|---|---|---|---|---|---|
| A1 | Ingestion | EH consumer | Kinesis consumer | valid→buffer→S3, invalid→DLQ | test_kinesis_consumer, e2e_moto | E-M2-1 | PASS |
| A2 | Raw/Bronze persistence | ADLS | S3 JSONL | immutable, date-partitioned, dup retained | e2e_moto | E-M2-1 | PASS |
| A3 | Checkpointing | file/blob | file+DynamoDB | after durable write; restart resume | dynamo/failure tests | E-M2-1, M11 | PASS |
| A4 | Deduplication | Silver dedup | identical | DQ2 Bronze2→Silver1 | local Spark | silver-evidence | PASS |
| A5 | Schema validation | Pydantic | identical | DQ3/4/5/6 → DLQ | telemetry_event, DQ tests | E1 | PASS |
| A6 | Invalid timestamp | Silver gate | identical | DQ7 dropped | local Spark | silver-evidence | PASS |
| A7 | Unknown asset | graceful | identical | DQ8 retained, not flattened | local Spark | silver-evidence | PASS |
| A8 | Silver canonicalisation | flatten | identical | DQ9/DQ10 null cols | local Spark | silver-evidence | PASS |
| A9 | Gold aggregation | notebooks | identical | health summary counts | local Spark | gold-evidence | PASS |
| A10 | ML features | leakage-safe | identical | 0 NULL feature cols, quarantine | feature_spec (17) | ml/E1 | PASS |
| A11 | Anomaly detection | IsolationForest | identical | deterministic scores | ml_reproducibility | ml-evidence | PASS |
| A12 | Threshold handling | max-F1 frozen | identical | deterministic threshold | ml_reproducibility | ml-evidence | PASS |
| A13 | Edge/cloud/hybrid modes | evidence tables | identical notebooks | mode routing | generate_bearing_events | E1 | PARTIAL (live tables NOT VERIFIED) |
| A14 | Escalation / CloudForest | job | identical (s3) | cloud_validation per escalation | contract | ml-evidence | PARTIAL |
| A15 | Mode switching | mode_history | identical | 4 transitions (C/E) | generate_bearing_events | E1 | PARTIAL |
| A16 | Cloud egress | gold | identical | payload sizing | payload_sizing (6) | E1 | PASS (offline) |
| A17 | Model/version lineage | MLflow | identical | dataset_run_id, feature_set_version, model_version | contract | ml-evidence | PASS |
| A18 | Scenario F metrics | generator | identical | TP=80/FP=5/FN=10/TN=5, F1≈0.914286 | generate_bearing_events | E1 | PASS (generator); live Gold NOT VERIFIED |
| A19 | Scenario B | generator | identical | agreement=0.5, cloud_acc=1.0 | generate_bearing_events | E1 | PASS (generator) |
| A20 | Observability | Azure Monitor | CloudWatch | lag/DLQ/failure alarms | checkov + coded | OBSERVABILITY | IMPLEMENTED (live NOT VERIFIED) |
| A21 | Security | KV/MI/RBAC | Secrets/IAM/KMS | least-priv, no static keys | checkov + secret scan | security-evidence | IMPLEMENTED |
| A22 | IaC | azurerm | AWS TF | validate + scan clean | hcl2 + checkov | terraform-evidence | IMPLEMENTED (apply NOT EXECUTED) |
| A23 | CI/CD | Actions OIDC | Actions AWS OIDC | no static keys, gates | YAML valid + local proxies | cicd-evidence | IMPLEMENTED (runs NOT EXECUTED) |
| A24 | DR / recovery | runbooks | failure suite + runbooks | predictable recovery | failure_recovery (5) | M11 | PASS (tested subset) |

The exact Azure numeric acceptance values are preserved and asserted at the
generator + local-Spark level. Reproducing them THROUGH deployed Gold tables is
the only remaining live-cluster gap (A13/A15/A18 "PARTIAL").
