#!/bin/bash
# LocalStack initialization script
# This runs automatically when LocalStack starts

echo "Initializing LocalStack AWS resources..."

# Wait for LocalStack to be ready
sleep 5

# Set AWS CLI to use LocalStack
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost:4566

# Create S3 buckets
echo "Creating S3 buckets..."
awslocal s3 mb s3://etl-raw-data-local
awslocal s3 mb s3://etl-processed-data-local
awslocal s3 mb s3://etl-archive-local

# Create DynamoDB table
echo "Creating DynamoDB table..."
awslocal dynamodb create-table \
    --table-name etl-metadata-local \
    --attribute-definitions \
        AttributeName=job_id,AttributeType=S \
        AttributeName=timestamp,AttributeType=S \
    --key-schema \
        AttributeName=job_id,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --provisioned-throughput \
        ReadCapacityUnits=5,WriteCapacityUnits=5

# Create SNS topic
echo "Creating SNS topic..."
awslocal sns create-topic --name etl-notifications-local

# Create EventBridge rule (disabled by default)
echo "Creating EventBridge rule..."
awslocal events put-rule \
    --name etl-schedule-local \
    --schedule-expression "rate(1 hour)" \
    --state DISABLED

# Upload sample data
echo "Uploading sample data..."
if [ -f /app/sample_data/sample_sales.csv ]; then
    awslocal s3 cp /app/sample_data/sample_sales.csv s3://etl-raw-data-local/sample/
fi

echo "LocalStack initialization complete!"
echo ""
echo "Resources created:"
echo "  - S3: etl-raw-data-local, etl-processed-data-local, etl-archive-local"
echo "  - DynamoDB: etl-metadata-local"
echo "  - SNS: etl-notifications-local"
echo "  - EventBridge: etl-schedule-local (disabled)"
