# ETL Pipeline - Technical Documentation

This document provides in-depth technical documentation for the AWS ETL Pipeline, covering architecture patterns, code structure, and AWS service integrations.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Medallion Architecture](#medallion-architecture)
3. [AWS Services Deep Dive](#aws-services-deep-dive)
4. [Code Structure](#code-structure)
5. [Data Flow](#data-flow)
6. [AWS QuickSight Integration](#aws-quicksight-integration)
7. [Key Patterns & Best Practices](#key-patterns--best-practices)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AWS ETL Pipeline Architecture                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┐     ┌─────────────┐     ┌──────────────┐     ┌───────────┐  │
│   │   S3     │────>│   Lambda    │────>│     S3       │────>│ QuickSight│  │
│   │  (Raw)   │     │ (Processor) │     │ (Processed)  │     │ (BI/Viz)  │  │
│   └──────────┘     └──────┬──────┘     └──────────────┘     └───────────┘  │
│        │                  │                                                  │
│        │           ┌──────┴──────┐                                          │
│        │           │             │                                          │
│        │      ┌────▼────┐  ┌─────▼─────┐                                   │
│        │      │DynamoDB │  │    SNS    │                                   │
│        │      │(Metadata)│  │(Notifications)                               │
│        │      └─────────┘  └───────────┘                                   │
│        │                                                                     │
│   ┌────▼────┐                                                               │
│   │   S3    │                                                               │
│   │(Archive)│                                                               │
│   └─────────┘                                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Purpose | AWS Service |
|-----------|---------|-------------|
| Raw Data Store | Landing zone for incoming data | S3 |
| ETL Processor | Extract, Transform, Load operations | Lambda |
| Processed Data Store | Cleaned, transformed data in Parquet | S3 |
| Metadata Store | Job tracking, statistics, history | DynamoDB |
| Notifications | Success/failure alerts | SNS |
| Archive | Long-term storage of processed files | S3 |
| Analytics | Business intelligence dashboards | QuickSight |

---

## Medallion Architecture

This pipeline implements the **Medallion Architecture** (also known as Multi-Hop Architecture), a data design pattern used to organize data in a lakehouse.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Medallion Architecture                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                │
│   │   BRONZE    │ ───> │   SILVER    │ ───> │    GOLD     │                │
│   │  (Raw Data) │      │  (Cleaned)  │      │ (Aggregated)│                │
│   └─────────────┘      └─────────────┘      └─────────────┘                │
│                                                                              │
│   - Original format    - Deduplicated      - Business-ready                 │
│   - No transformations - Type-casted       - Aggregations                   │
│   - Audit trail        - Null-handled      - KPIs & Metrics                 │
│   - CSV, JSON, etc.    - Validated         - Parquet format                 │
│                        - Parquet format                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer Details

#### Bronze Layer (Raw Zone)
- **Location**: `s3://etl-pipeline-{env}-raw-data-{account}/incoming/`
- **Format**: CSV, JSON (original format)
- **Purpose**: Preserve raw data exactly as received
- **Retention**: 7 days (configurable)

```python
# Bronze layer - raw data ingestion
raw_data = extractor.extract(source_info)
# Data is read as-is, no transformations
```

#### Silver Layer (Cleaned Zone)
- **Location**: `s3://etl-pipeline-{env}-processed-data-{account}/processed/`
- **Format**: Parquet (columnar, compressed)
- **Purpose**: Cleaned, validated, deduplicated data

Transformations applied:
```python
# Silver layer transformations (transformer.py)
df = self._clean_column_names(df)      # Standardize columns
df = self._handle_nulls(df)            # Handle missing values
df = self._remove_duplicates(df)       # Deduplicate
df = self._cast_types(df)              # Proper data types
df = self._add_derived_fields(df)      # Add metadata
```

#### Gold Layer (Business Zone)
- **Location**: Can be created via additional transformations or views
- **Format**: Parquet or database tables
- **Purpose**: Business-ready aggregations for analytics

Example Gold layer aggregations:
```python
# Example: Daily sales summary (Gold layer)
gold_df = silver_df.groupby(['_year', '_month', '_day']).agg({
    'quantity': 'sum',
    'unit_price': 'mean',
    'total': 'sum'
}).reset_index()
```

### Partitioning Strategy

Data is partitioned by date for efficient querying:

```
processed/
├── year=2024/
│   ├── month=01/
│   │   ├── day=15/
│   │   │   └── etl-20240115-143052.parquet
│   │   └── day=16/
│   │       └── etl-20240116-091523.parquet
│   └── month=02/
│       └── ...
```

This enables:
- **Partition pruning** in Athena/QuickSight queries
- **Cost optimization** by scanning only relevant data
- **Time-based data lifecycle** management

---

## AWS Services Deep Dive

### 1. AWS Lambda

Lambda is the compute engine that runs the ETL logic.

#### AWS SDK Pandas Layer

To keep the deployment package under 250MB, heavy dependencies are provided by an AWS Lambda Layer:

```hcl
layers = [
  "arn:aws:lambda:${var.aws_region}:336392948345:layer:AWSSDKPandas-Python39:28"
]
```

**Layer provides:**
- pandas
- numpy
- pyarrow
- AWS SDK utilities

**Why use a layer?**

| Without Layer | With Layer |
|---------------|------------|
| Package size: ~300MB | Package size: ~5MB |
| Exceeds 250MB limit | Well under limit |
| Slow deployments | Fast deployments |
| Complex dependency management | Simple requirements file |

The `requirements-lambda.txt` only includes lightweight dependencies:

```txt
# requirements-lambda.txt
pyyaml>=6.0
aws-lambda-powertools>=2.20.0
# pandas, numpy, pyarrow provided by AWS SDK Pandas Layer
```

See [AWS SDK Pandas Layer documentation](https://aws-sdk-pandas.readthedocs.io/en/stable/layers.html) for more details.

#### Lambda Handler Pattern

```python
# lambda_handler.py

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Entry point for Lambda invocation.

    Args:
        event: Trigger payload (S3 event, EventBridge, or direct)
        context: Lambda runtime context (request ID, memory, timeout)

    Returns:
        Response with status code and job results
    """
    job_id = f"etl-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    try:
        # ETL Pipeline
        raw_data = extractor.extract(source_info)
        transformed_data, stats = transformer.transform(raw_data)
        load_result = loader.load(transformed_data, job_id)

        return {"statusCode": 200, "body": {...}}
    except Exception as e:
        return {"statusCode": 500, "body": {"error": str(e)}}
```

#### Event Sources

Lambda can be triggered by multiple sources:

```python
def _parse_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse incoming event to determine trigger type."""

    # 1. S3 Event (automatic on file upload)
    if "Records" in event and "s3" in event["Records"][0]:
        return {
            "type": "s3",
            "bucket": event["Records"][0]["s3"]["bucket"]["name"],
            "key": event["Records"][0]["s3"]["object"]["key"]
        }

    # 2. EventBridge (scheduled)
    if event.get("source") == "aws.events":
        return {"type": "scheduled", ...}

    # 3. Direct invocation (manual)
    if "source_bucket" in event:
        return {"type": "direct", ...}
```

#### Lambda Configuration

```hcl
# Terraform configuration
resource "aws_lambda_function" "etl_processor" {
  function_name = "etl-pipeline-dev-processor"
  runtime       = "python3.9"
  handler       = "lambda_handler.handler"
  memory_size   = 256    # MB - needed for pandas operations
  timeout       = 300    # seconds (5 min max for ETL)

  # AWS SDK Pandas Layer - provides pandas, numpy, pyarrow
  layers = [
    "arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python39:28"
  ]

  environment {
    variables = {
      ENVIRONMENT         = "dev"
      S3_RAW_BUCKET       = aws_s3_bucket.raw_data.id
      S3_PROCESSED_BUCKET = aws_s3_bucket.processed_data.id
      DYNAMODB_TABLE      = aws_dynamodb_table.metadata.name
      SNS_TOPIC_ARN       = aws_sns_topic.notifications.arn
    }
  }
}
```

### 2. Boto3 (AWS SDK for Python)

Boto3 is used throughout for AWS service interactions.

#### Client vs Resource Pattern

```python
# aws_clients.py

class AWSClients:
    """Centralized AWS client management."""

    def _get_client_kwargs(self) -> dict:
        """Configure boto3 clients with retry logic."""
        return {
            "region_name": self.region,
            "config": BotoConfig(
                retries={"max_attempts": 3, "mode": "adaptive"}
            )
        }

    @property
    def s3(self):
        """Low-level S3 client for operations."""
        if self._s3 is None:
            self._s3 = boto3.client("s3", **self._get_client_kwargs())
        return self._s3

    @property
    def dynamodb_resource(self):
        """High-level DynamoDB resource for Table operations."""
        return boto3.resource("dynamodb", **self._get_client_kwargs())
```

#### S3 Operations

```python
# extractor.py - Reading from S3

def _extract_csv(self, bucket: str, key: str) -> pd.DataFrame:
    """Extract CSV file from S3."""
    response = self.s3.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read().decode("utf-8")
    return pd.read_csv(io.StringIO(content))

# loader.py - Writing to S3

def _write_to_s3(self, df: pd.DataFrame, bucket: str, key: str):
    """Write DataFrame to S3 as Parquet."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine="pyarrow", compression="snappy")
    buffer.seek(0)

    self.s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream"
    )
```

#### LocalStack Support

The code supports LocalStack for local development:

```python
def _get_client_kwargs(self) -> dict:
    kwargs = {"region_name": self.region, ...}

    # Local development with LocalStack
    if self.is_local and self.endpoint_url:
        kwargs["endpoint_url"] = self.endpoint_url  # http://localhost:4566
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"

    return kwargs
```

### 3. Amazon DynamoDB

DynamoDB stores ETL job metadata for tracking and auditing.

#### Table Schema

```
Table: etl-pipeline-dev-metadata

Primary Key:
  - job_id (Partition Key) - String
  - timestamp (Sort Key) - String (ISO format)

Attributes:
  - status: RUNNING | SUCCESS | FAILED
  - started_at: ISO timestamp
  - completed_at: ISO timestamp
  - duration_seconds: Number
  - job_result: Map (statistics)
  - error_message: String (if failed)
  - trigger_event: Map (original event)
```

#### DynamoDB Operations

```python
# metadata.py

class MetadataManager:
    """Manages ETL job metadata in DynamoDB."""

    def start_job(self, job_id: str, event: Dict) -> bool:
        """Record job start."""
        table = self.aws.dynamodb_resource.Table(self.table_name)

        table.put_item(Item={
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "RUNNING",
            "trigger_event": event
        })

    def complete_job(self, job_id: str, result: Dict) -> bool:
        """Update job as completed."""
        table.update_item(
            Key={"job_id": job_id, "timestamp": self._get_job_timestamp(job_id)},
            UpdateExpression="SET #status = :status, job_result = :result",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "SUCCESS",
                ":result": result
            }
        )
```

#### DynamoDB Best Practices Used

1. **Reserved Keywords**: Use `ExpressionAttributeNames` for reserved words
   ```python
   ExpressionAttributeNames={"#status": "status"}  # 'status' is reserved
   ```

2. **Type Conversion**: DynamoDB doesn't support float, use Decimal
   ```python
   def _convert_to_dynamodb_types(obj):
       if isinstance(obj, float):
           return Decimal(str(obj))
   ```

3. **TTL for Cleanup**: Auto-delete old records
   ```hcl
   ttl {
     attribute_name = "ttl"
     enabled        = true
   }
   ```

### 4. Amazon SNS

SNS sends notifications for job success/failure.

#### Publishing Notifications

```python
# aws_clients.py

def send_notification(self, subject: str, message: str) -> Optional[str]:
    """Send notification via SNS."""
    topic_arn = os.environ.get("SNS_TOPIC_ARN")

    response = self.sns.publish(
        TopicArn=topic_arn,
        Subject=subject[:100],  # SNS subject limit
        Message=message
    )
    return response["MessageId"]
```

#### Notification Content

```python
# Success notification
aws_clients.send_notification(
    subject=f"ETL Job Success: {job_id}",
    message=json.dumps({
        "job_id": job_id,
        "status": "SUCCESS",
        "duration_seconds": 4.2,
        "rows_processed": 100,
        "output_location": "s3://..."
    }, indent=2)
)

# Failure notification
aws_clients.send_notification(
    subject=f"ETL Job FAILED: {job_id}",
    message=f"Error: {error_message}\n\nTraceback:\n{traceback}"
)
```

### 5. Amazon S3

S3 is used for data storage at all stages.

#### Bucket Structure

```
etl-pipeline-dev-raw-data-{account}/
├── incoming/              # Landing zone for new files
│   ├── sales_2024.csv
│   └── orders_2024.json
└── archived/              # Processed files moved here

etl-pipeline-dev-processed-data-{account}/
├── lambda-code/           # Lambda deployment package
│   └── lambda_function.zip
└── processed/             # Transformed data (Parquet)
    └── year=2024/
        └── month=11/
            └── day=30/
                └── etl-20241130-143052.parquet
```

#### S3 Event Trigger

```hcl
# Terraform - S3 notification to trigger Lambda
resource "aws_s3_bucket_notification" "raw_data_notification" {
  bucket = aws_s3_bucket.raw_data.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.etl_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
    filter_suffix       = ".csv"
  }
}
```

---

## Code Structure

```
etl/
├── lambda_handler.py          # Lambda entry point
├── requirements-lambda.txt    # Lambda dependencies
├── README.md                  # This documentation
│
└── src/
    ├── extract/
    │   ├── __init__.py
    │   └── extractor.py       # Data extraction from S3
    │
    ├── transform/
    │   ├── __init__.py
    │   └── transformer.py     # Data transformation logic
    │
    ├── load/
    │   ├── __init__.py
    │   └── loader.py          # Data loading to S3
    │
    └── utils/
        ├── __init__.py
        ├── aws_clients.py     # Boto3 client management
        ├── config.py          # Configuration management
        └── metadata.py        # DynamoDB metadata manager
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `lambda_handler.py` | Orchestrates ETL flow, handles events |
| `extractor.py` | Reads CSV/JSON/Parquet from S3 |
| `transformer.py` | Cleans, validates, transforms data |
| `loader.py` | Writes Parquet to S3 with partitioning |
| `aws_clients.py` | Manages boto3 clients, LocalStack support |
| `config.py` | YAML config + environment variables |
| `metadata.py` | DynamoDB job tracking |

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ETL Data Flow                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. TRIGGER                                                                  │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ S3 Upload ──> S3 Event ──> Lambda Invocation                     │    │
│     │    or                                                             │    │
│     │ EventBridge Schedule ──> Lambda Invocation                       │    │
│     │    or                                                             │    │
│     │ Manual Invoke ──> Lambda Invocation                              │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  2. EXTRACT                                                                  │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ S3 (raw) ──> boto3.get_object() ──> pandas.DataFrame             │    │
│     │                                                                   │    │
│     │ Supported: CSV, JSON, Parquet                                    │    │
│     │ Output: Raw DataFrame (no transformations)                       │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  3. TRANSFORM                                                                │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ Raw DataFrame                                                     │    │
│     │   │                                                               │    │
│     │   ├──> Clean column names (lowercase, remove special chars)      │    │
│     │   ├──> Handle nulls (drop/fill/flag)                             │    │
│     │   ├──> Remove duplicates                                         │    │
│     │   ├──> Cast types (dates, numbers)                               │    │
│     │   ├──> Add derived fields (_processed_at, _row_hash, partitions) │    │
│     │   └──> Validate data quality                                     │    │
│     │   │                                                               │    │
│     │   v                                                               │    │
│     │ Cleaned DataFrame + Statistics                                   │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  4. LOAD                                                                     │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ Cleaned DataFrame                                                 │    │
│     │   │                                                               │    │
│     │   ├──> Convert to Parquet (snappy compression)                   │    │
│     │   ├──> Generate partitioned path (year/month/day)                │    │
│     │   └──> boto3.put_object() ──> S3 (processed)                     │    │
│     │                                                                   │    │
│     │ Also: Archive original file (optional)                           │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  5. METADATA & NOTIFICATIONS                                                 │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ Job Start ──> DynamoDB.put_item(status=RUNNING)                  │    │
│     │ Job End ──> DynamoDB.update_item(status=SUCCESS/FAILED)          │    │
│     │ Notification ──> SNS.publish(job_summary)                        │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AWS QuickSight Integration

Amazon QuickSight can visualize the processed data directly from S3.

### Setting Up QuickSight

#### 1. Create S3 Data Source

```
1. Open QuickSight Console
2. Go to "Datasets" > "New dataset"
3. Select "S3" as the data source
4. Create a manifest file (see below)
5. Upload or reference the manifest
```

#### 2. S3 Manifest File

Create `quicksight-manifest.json`:

```json
{
  "fileLocations": [
    {
      "URIPrefixes": [
        "s3://etl-pipeline-dev-processed-data-{account}/processed/"
      ]
    }
  ],
  "globalUploadSettings": {
    "format": "PARQUET"
  }
}
```

#### 3. Alternative: Use Amazon Athena

For more complex queries, use Athena as an intermediary:

```sql
-- Create external table in Athena
CREATE EXTERNAL TABLE etl_processed_data (
    order_id STRING,
    customer_name STRING,
    product STRING,
    quantity INT,
    unit_price DOUBLE,
    order_date TIMESTAMP,
    _processed_at TIMESTAMP,
    _row_hash BIGINT
)
PARTITIONED BY (
    _year INT,
    _month INT,
    _day INT
)
STORED AS PARQUET
LOCATION 's3://etl-pipeline-dev-processed-data-{account}/processed/'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

-- Load partitions
MSCK REPAIR TABLE etl_processed_data;

-- Query example
SELECT
    _year, _month, _day,
    COUNT(*) as order_count,
    SUM(quantity * unit_price) as total_revenue
FROM etl_processed_data
GROUP BY _year, _month, _day
ORDER BY _year, _month, _day;
```

#### 4. QuickSight Dashboard Ideas

| Dashboard | Metrics | Visualization |
|-----------|---------|---------------|
| Sales Overview | Total revenue, order count | KPI cards, line chart |
| Daily Trends | Orders by day | Time series |
| Product Performance | Revenue by product | Bar chart, pie chart |
| ETL Job Monitoring | Job success rate, duration | Status indicators |

### Connecting QuickSight to Athena

```
1. In QuickSight, create new dataset
2. Select "Athena" as source
3. Choose your database and table
4. Select "Direct query" for real-time data
5. Create visualizations
```

---

## Key Patterns & Best Practices

### 1. Environment Variable Configuration

```python
# Use environment variables for AWS resource names
bucket = os.environ.get("S3_PROCESSED_BUCKET")
table = os.environ.get("DYNAMODB_TABLE")
topic_arn = os.environ.get("SNS_TOPIC_ARN")

# Fallback for local development
if not bucket:
    bucket = f"etl-processed-data-{env}"
```

### 2. Graceful Error Handling

```python
def send_notification(self, subject: str, message: str):
    try:
        response = self.sns.publish(...)
        return response["MessageId"]
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return None  # Don't fail ETL for notification errors
```

### 3. Idempotency

```python
# Add row hash for deduplication tracking
df["_row_hash"] = pd.util.hash_pandas_object(df, index=False)

# Use job_id in output path for unique files
output_path = f"processed/year={year}/month={month}/day={day}/{job_id}.parquet"
```

### 4. Observability

```python
# Comprehensive logging
logger.info(f"Starting ETL job: {job_id}")
logger.info(f"Extracted {len(df)} rows from {source}")
logger.info(f"Transformation complete: {stats}")
logger.error(f"ETL job failed: {error}")

# Job statistics for monitoring
stats = {
    "input_rows": 100,
    "output_rows": 98,
    "duplicates_removed": 2,
    "nulls_handled": 5,
    "duration_seconds": 4.2
}
```

### 5. Cost Optimization (Free Tier)

```hcl
# Lambda - minimal memory for free tier
memory_size = 256  # Increased only for pandas requirement

# DynamoDB - minimal capacity
read_capacity  = 5
write_capacity = 5

# S3 - lifecycle rules to delete old data
expiration {
  days = 30
}

# CloudWatch - short log retention
retention_in_days = 7
```

---

## Testing

### Local Testing with LocalStack

```bash
# Start LocalStack
docker-compose up -d localstack

# Run ETL locally
python scripts/run_local.py --full-test
```

### Unit Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=etl --cov-report=html
```

### Integration Tests

```bash
# Run against LocalStack
pytest tests/integration/ -v
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `No module named 'pandas'` | Dependencies not in Lambda package | Run `python scripts/build_lambda.py` |
| `NoSuchBucket` | Wrong bucket name | Check `S3_PROCESSED_BUCKET` env var |
| `AccessDenied` on DynamoDB | IAM permissions | Check Lambda role policy |
| `Reserved keyword` in DynamoDB | Using reserved words as attributes | Use `ExpressionAttributeNames` |

### Debugging Lambda

```bash
# View recent logs
aws logs tail /aws/lambda/etl-pipeline-dev-processor --since 30m

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/etl-pipeline-dev-processor \
  --filter-pattern "ERROR"
```

---

## Further Reading

- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
- [Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [Medallion Architecture](https://www.databricks.com/glossary/medallion-architecture)
- [Amazon QuickSight User Guide](https://docs.aws.amazon.com/quicksight/latest/user/)
