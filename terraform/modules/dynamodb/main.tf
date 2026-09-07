# DynamoDB checkpoint lease table — production consumer checkpoint store
# (see consumer/dynamo_checkpoint.py). PITR + KMS. partition_id is the shard key.

resource "aws_dynamodb_table" "checkpoints" {
  name         = "${var.name_prefix}-checkpoints"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "partition_id"

  attribute {
    name = "partition_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = var.tags
}
