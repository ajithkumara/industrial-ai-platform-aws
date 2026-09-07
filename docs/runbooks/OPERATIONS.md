# OPERATIONS.md — AWS operational runbooks

## RB-01 — Consumer lag (`*-consumer-lag` alarm)
1. Check `GetRecords.IteratorAgeMilliseconds` trend (CloudWatch).
2. Confirm the consumer task is running (ECS/EKS/EC2) and not crash-looping
   (consumer log group).
3. If down: restart the task — it resumes from the DynamoDB lease (no loss).
4. If up but behind: shard throughput exceeded — increase shard count
   (`terraform apply -var kinesis shard_count=N`) or enable enhanced fan-out.

## RB-02 — No incoming records (`*-no-incoming-records`)
1. Confirm producers / NATS bridge are running.
2. Check Kinesis `PutRecord` errors on the producer side.
3. Verify the stream exists and the producer role can `PutRecords`.

## RB-03 — DLQ volume (`*-dlq-volume`)
1. List recent DLQ objects: `aws s3 ls s3://<bucket>/raw/telemetry/_dlq/ --recursive`.
2. Inspect `error_reason` in a sample object — malformed JSON vs schema gate.
3. If a producer regression: fix the producer, then replay DLQ objects through
   the consumer path (raw_body is preserved).

## RB-04 — Pipeline / ML job failure
1. Open the DLT pipeline / Job run in Databricks; read the event log.
2. For DLT expectation aborts: check `quarantine_telemetry_events`.
3. For ML: confirm `dataset_run_id` data landed in Gold before retraining.

## RB-05 — Security / audit
1. CloudTrail: `aws cloudtrail lookup-events` for the actor/action.
2. VPC flow logs for unexpected network flows.
