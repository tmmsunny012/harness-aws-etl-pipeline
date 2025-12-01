"""
Pytest Configuration and Fixtures
=================================
Shared fixtures for all tests.
"""

import os
import pytest
import boto3
from moto import mock_aws
import pandas as pd

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame({
        "order_id": ["ORD001", "ORD002", "ORD003"],
        "customer_id": ["CUST001", "CUST002", "CUST001"],
        "product_name": ["Laptop", "Mouse", "Keyboard"],
        "quantity": [1, 2, 1],
        "unit_price": [999.99, 29.99, 149.99],
        "order_date": ["2024-01-15", "2024-01-16", "2024-01-17"],
        "status": ["completed", "shipped", "processing"]
    })


@pytest.fixture
def sample_dataframe_with_nulls():
    """Create a sample DataFrame with null values."""
    return pd.DataFrame({
        "order_id": ["ORD001", "ORD002", None],
        "customer_id": ["CUST001", None, "CUST003"],
        "product_name": ["Laptop", "Mouse", "Keyboard"],
        "quantity": [1, 2, None],
        "unit_price": [999.99, None, 149.99],
        "order_date": ["2024-01-15", "2024-01-16", "2024-01-17"],
        "status": ["completed", "shipped", None]
    })


@pytest.fixture
def sample_csv_content():
    """Sample CSV content as bytes."""
    return b"""order_id,customer_id,product_name,quantity,unit_price
ORD001,CUST001,Laptop,1,999.99
ORD002,CUST002,Mouse,2,29.99
ORD003,CUST001,Keyboard,1,149.99
"""


@pytest.fixture
def sample_json_content():
    """Sample JSON lines content as bytes."""
    return b"""{"order_id": "ORD001", "customer_id": "CUST001", "product_name": "Laptop"}
{"order_id": "ORD002", "customer_id": "CUST002", "product_name": "Mouse"}
"""


@pytest.fixture
def aws_credentials():
    """Mock AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_s3(aws_credentials):
    """Mock S3 service."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        # Create test buckets
        s3.create_bucket(Bucket="etl-raw-data-test")
        s3.create_bucket(Bucket="etl-processed-data-test")
        yield s3


@pytest.fixture
def mock_dynamodb(aws_credentials):
    """Mock DynamoDB service."""
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        # Create test table
        dynamodb.create_table(
            TableName="etl-metadata-test",
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"}
            ],
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"}
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        )
        yield dynamodb


@pytest.fixture
def mock_sns(aws_credentials):
    """Mock SNS service."""
    with mock_aws():
        sns = boto3.client("sns", region_name="us-east-1")
        sns.create_topic(Name="etl-notifications-test")
        yield sns


@pytest.fixture
def mock_config():
    """Mock configuration object."""
    class MockConfig:
        def __init__(self):
            self._config = {
                "s3.raw_bucket_prefix": "etl-raw-data",
                "s3.processed_bucket_prefix": "etl-processed-data",
                "dynamodb.table_name": "etl-metadata",
                "sns.topic_name": "etl-notifications",
                "etl.transform.null_handling": "drop",
                "etl.load.output_format": "parquet",
                "etl.load.compression": "snappy"
            }

        def get(self, key, default=None):
            return self._config.get(key, default)

    return MockConfig()
