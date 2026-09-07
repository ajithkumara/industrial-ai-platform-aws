# AWS_COST_AND_SCALE.md — Milestone 14

> Cost DRIVERS and sizing by tier. **No specific dollar prices are quoted** —
> AWS pricing changes by region/date and was not verified here; use the AWS
> Pricing Calculator with the drivers below. Reliability controls are never
> optimised away.

## Cost drivers (what to watch)

| Service | Primary driver | Notes |
|---|---|---|
| Kinesis | shard-hours + PUT payload units + (enhanced fan-out consumers) | 1 shard ≈ 1MB/s in, 1000 rec/s |
| S3 | stored GB + PUT/GET requests + lifecycle transitions | lifecycle → IA/Glacier cuts cold cost |
| DynamoDB | on-demand read/write request units | checkpoint cadence is low → cheap |
| Databricks | DBU-hours (serverless) | dominant cost; scale clusters to workload |
| KMS | key-months + request volume | trivial vs data services |
| CloudWatch | ingested log GB + alarms + custom metrics | 365-day retention drives log cost |
| CloudTrail | first trail free; data events extra | management events cheap |
| VPC | interface-endpoint-hours + data processed; NAT if added | gateway endpoints (S3/DynamoDB) are free |
| ECR | stored GB + data transfer | small |
| Data transfer | cross-AZ / egress | keep traffic on VPC endpoints |

## Sizing tiers

| Tier | Kinesis | Databricks | S3 lifecycle | CloudWatch retention | Notes |
|---|---|---|---|---|---|
| **Dev** | 1 shard | serverless, on-demand jobs | IA@30/Glacier@90 | lower (e.g. 30d) to cut cost | single AZ ok |
| **Small prod** | 1–2 shards | serverless, scheduled | as dev | 365d | 2 AZ, alarms on |
| **Medium prod** | 4–8 shards, enhanced fan-out | job clusters sized to SLA | + intelligent-tiering | 365d | multi-AZ, budget alerts |
| **Large prod** | on-demand stream mode / many shards | autoscaling + pools | CRR for DR | 365d+ | multi-region DR |

## Scale-to-zero / controls

- Jobs are on-demand/scheduled (no idle clusters); DLT `continuous: false`.
- S3 lifecycle tiers cold data automatically; abort-incomplete-multipart at 7d.
- **Budget alerts** (recommended): add `aws_budgets_budget` with email at 80% —
  the Azure reference had a subscription budget (ALERT-03); the AWS analogue is
  a backlog item B-M14-BUDGET (P2).
- Kinesis: start at 1 shard (dev) and scale on the `IteratorAge` alarm, not
  preemptively.

## Reliability NOT optimised away

Versioning, PITR, multi-region CloudTrail, KMS, flow logs, and `prevent_destroy`
stay on in every tier — they are correctness/security controls, not discretionary
cost.
