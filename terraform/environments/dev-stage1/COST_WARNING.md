# Stage 1 — Minimum Viable Ingestion

**Estimated cost: ~$0.015 for a 1-hour session. Destroy immediately after testing.**

## What this creates

| Resource | Count | Cost |
|---|---|---|
| Kinesis Data Stream | 1 shard, 24h retention | $0.015/hr + PUT units |
| S3 bucket | AWS-managed SSE (not CMK) | Free Tier 5GB; pennies for tiny data |
| DynamoDB table | on-demand, AWS-managed | Free Tier 25 WCU/RCU |
| IAM roles (consumer + producer) | 2 | Free |

## What is intentionally NOT here (vs full dev environment)

- ❌ KMS CMKs — saves $6+/month (6 × $1/key). Use full dev env for CMKs.
- ❌ VPC interface endpoints — saves ~$14/month. Default VPC, public Kinesis endpoint.
- ❌ CloudTrail — saves S3 storage cost. Add in Stage 2.
- ❌ Secrets Manager — saves $0.80/month. Credentials via env vars / instance profile.
- ❌ ECR — no image built yet.
- ❌ CloudWatch alarms — add in Stage 2.
- ❌ 168h Kinesis retention — saves $0.55/day. 24h is sufficient for Stage 1 testing.

## Cleanup (run immediately after testing)

```bash
cd terraform/environments/dev-stage1
terraform destroy -var-file=terraform.tfvars
```

Then verify in the AWS Console:
- Kinesis: stream deleted
- S3: bucket empty + deleted (Terraform destroy fails if bucket has objects — empty it first)
- DynamoDB: table deleted
- IAM: roles deleted

## Free Tier limits relevant here

- S3: 5GB storage, 20K GET, 2K PUT per month — Stage 1 test data is well within this.
- DynamoDB: 25 WCU + 25 RCU provisioned (we use on-demand; Free Tier covers first 25 writes/reads).
- Kinesis: NO Free Tier — $0.015/shard-hr from the first second. **Destroy after testing.**
