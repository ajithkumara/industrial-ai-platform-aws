"""
Tests for consumer/dynamo_checkpoint.py (DynamoDB lease checkpoint store),
using moto to emulate DynamoDB.

Proves the production checkpoint store is interface-compatible with the
local-file FileCheckpointManager AND survives a consumer restart — the AWS
equivalent of the Azure blob checkpoint durability contract.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from consumer.dynamo_checkpoint import DynamoCheckpointManager

_TABLE = "industrial-ai-checkpoints"
_REGION = "ca-central-1"


@pytest.fixture
def dynamo_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        ddb.create_table(
            TableName=_TABLE,
            KeySchema=[{"AttributeName": "partition_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "partition_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield ddb


def test_update_and_get_checkpoint(dynamo_table):
    mgr = DynamoCheckpointManager(_TABLE, region=_REGION, dynamodb_resource=dynamo_table)
    mgr.update_checkpoint("shardId-000000000000", offset="49590", sequence_number="49590")

    cp = mgr.get_checkpoint("shardId-000000000000")
    assert cp["offset"] == "49590"
    assert cp["sequence_number"] == "49590"


def test_starting_position_defaults_to_beginning_when_absent(dynamo_table):
    mgr = DynamoCheckpointManager(_TABLE, region=_REGION, dynamodb_resource=dynamo_table)
    assert mgr.get_starting_position("shardId-unknown") == "-1"


def test_restart_recovery_reads_committed_checkpoint(dynamo_table):
    # First consumer instance commits a checkpoint.
    mgr1 = DynamoCheckpointManager(_TABLE, region=_REGION, dynamodb_resource=dynamo_table)
    mgr1.update_checkpoint("shardId-000000000001", offset="777", sequence_number="777")

    # Simulate a restart: a brand-new manager instance must recover it from
    # DynamoDB (not from any in-process state).
    mgr2 = DynamoCheckpointManager(_TABLE, region=_REGION, dynamodb_resource=dynamo_table)
    cp = mgr2.get_checkpoint("shardId-000000000001")
    assert cp is not None
    assert cp["sequence_number"] == "777"
    assert mgr2.get_starting_position("shardId-000000000001") == "777"


def test_checkpoint_write_failure_is_non_fatal(dynamo_table):
    # Point at a non-existent table so put_item raises; update_checkpoint must
    # swallow it (data already durable in S3) and still update the in-memory
    # mirror, matching the at-least-once contract.
    mgr = DynamoCheckpointManager(_TABLE, region=_REGION, dynamodb_resource=dynamo_table)
    mgr._table = dynamo_table.Table("does-not-exist")
    mgr.update_checkpoint("shardId-x", offset="1", sequence_number="1")  # must not raise
    assert mgr.checkpoints["shardId-x"]["sequence_number"] == "1"
