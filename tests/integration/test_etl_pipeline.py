"""
Integration Tests for ETL Pipeline
===================================
These tests require LocalStack to be running.
Run with: docker-compose up -d localstack && pytest tests/integration/ -v
"""

import os
import pytest
import boto3
import pandas as pd
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Skip all tests if LocalStack is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION", "false").lower() == "true",
    reason="Integration tests skipped (SKIP_INTEGRATION=true)"
)


def is_localstack_running():
    """Check if LocalStack is running."""
    try:
        import requests
        response = requests.get("http://localhost:4566/_localstack/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def localstack_available():
    """Skip tests if LocalStack is not running."""
    if not is_localstack_running():
        pytest.skip("LocalStack is not running")


@pytest.fixture(scope="module")
def local_env():
    """Set up local environment variables."""
    os.environ["ENVIRONMENT"] = "local"
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"
    yield
    # Cleanup
    del os.environ["AWS_ENDPOINT_URL"]


@pytest.fixture(scope="module")
def s3_client(local_env, localstack_available):
    """Create S3 client for LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1"
    )


@pytest.fixture(scope="module")
def dynamodb_client(local_env, localstack_available):
    """Create DynamoDB client for LocalStack."""
    return boto3.client(
        "dynamodb",
        endpoint_url="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1"
    )


@pytest.fixture(scope="module")
def setup_resources(s3_client, dynamodb_client):
    """Set up test resources in LocalStack."""
    # Create buckets
    for bucket in ["etl-raw-data-local", "etl-processed-data-local"]:
        try:
            s3_client.create_bucket(Bucket=bucket)
        except s3_client.exceptions.BucketAlreadyOwnedByYou:
            pass

    # Create DynamoDB table
    try:
        dynamodb_client.create_table(
            TableName="etl-metadata-local",
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
    except dynamodb_client.exceptions.ResourceInUseException:
        pass

    yield

    # Cleanup is handled by LocalStack container reset


class TestETLPipelineIntegration:
    """Integration tests for the complete ETL pipeline."""

    def test_s3_bucket_creation(self, s3_client, setup_resources):
        """Test that S3 buckets were created."""
        response = s3_client.list_buckets()
        bucket_names = [b["Name"] for b in response["Buckets"]]

        assert "etl-raw-data-local" in bucket_names
        assert "etl-processed-data-local" in bucket_names

    def test_upload_and_read_csv(self, s3_client, setup_resources):
        """Test uploading and reading CSV from S3."""
        # Upload test data
        csv_content = b"id,name,value\n1,test,100\n2,test2,200"
        s3_client.put_object(
            Bucket="etl-raw-data-local",
            Key="test/sample.csv",
            Body=csv_content
        )

        # Read back
        response = s3_client.get_object(
            Bucket="etl-raw-data-local",
            Key="test/sample.csv"
        )
        content = response["Body"].read()

        assert content == csv_content

    def test_dynamodb_table_exists(self, dynamodb_client, setup_resources):
        """Test that DynamoDB table was created."""
        response = dynamodb_client.list_tables()
        assert "etl-metadata-local" in response["TableNames"]

    def test_dynamodb_write_and_read(self, dynamodb_client, setup_resources):
        """Test writing and reading from DynamoDB."""
        # Write item
        dynamodb_client.put_item(
            TableName="etl-metadata-local",
            Item={
                "job_id": {"S": "test-job-001"},
                "timestamp": {"S": "2024-01-15T10:00:00"},
                "status": {"S": "SUCCESS"}
            }
        )

        # Read item
        response = dynamodb_client.get_item(
            TableName="etl-metadata-local",
            Key={
                "job_id": {"S": "test-job-001"},
                "timestamp": {"S": "2024-01-15T10:00:00"}
            }
        )

        assert "Item" in response
        assert response["Item"]["status"]["S"] == "SUCCESS"

    def test_full_etl_pipeline(self, s3_client, setup_resources, local_env):
        """Test the complete ETL pipeline flow."""
        from etl.src.utils.config import Config
        from etl.src.utils.aws_clients import AWSClients
        from etl.src.extract.extractor import DataExtractor
        from etl.src.transform.transformer import DataTransformer
        from etl.src.load.loader import DataLoader

        # Upload sample data
        sample_csv = b"""order_id,customer_id,product,quantity,price
ORD001,CUST001,Laptop,1,999.99
ORD002,CUST002,Mouse,2,29.99
ORD003,CUST003,Keyboard,1,149.99
"""
        s3_client.put_object(
            Bucket="etl-raw-data-local",
            Key="integration_test/sample.csv",
            Body=sample_csv
        )

        # Run ETL
        config = Config()
        aws_clients = AWSClients(config)

        # Extract
        extractor = DataExtractor(aws_clients, config)
        source_info = {
            "type": "direct",
            "bucket": "etl-raw-data-local",
            "key": "integration_test/sample.csv"
        }
        raw_data = extractor.extract(source_info)

        assert len(raw_data) == 3
        assert "order_id" in raw_data.columns

        # Transform
        transformer = DataTransformer(config)
        transformed_data, stats = transformer.transform(raw_data)

        assert stats["input_rows"] == 3
        assert "_processed_at" in transformed_data.columns

        # Load
        loader = DataLoader(aws_clients, config)
        result = loader.load(transformed_data, "integration-test-001")

        assert result["status"] == "success"
        assert result["rows_loaded"] == 3
