# Terraform Infrastructure

This directory contains the Terraform configuration for deploying the AWS ETL Pipeline infrastructure.

## Overview

The infrastructure is deployed using Terraform with an S3 backend for remote state management. This ensures:
- State persistence across CI/CD runs
- State locking to prevent concurrent modifications
- State versioning for recovery

## Architecture

```
infrastructure/
├── terraform/              # Main infrastructure
│   ├── main.tf            # Resource definitions
│   ├── variables.tf       # Input variables
│   ├── outputs.tf         # Output values
│   └── README.md          # This file
│
└── terraform-state/        # Bootstrap (state backend)
    └── main.tf            # S3 bucket + DynamoDB table
```

## State Management

### Remote State Backend

The infrastructure uses an S3 backend with DynamoDB locking:

```hcl
backend "s3" {
  bucket         = "etl-pipeline-terraform-state-{ACCOUNT_ID}"
  key            = "etl-pipeline/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "etl-pipeline-terraform-locks"
}
```

### Why S3 Backend?

| Feature | Benefit |
|---------|---------|
| **Remote Storage** | State persists between CI/CD runs |
| **State Locking** | DynamoDB prevents concurrent modifications |
| **Encryption** | State file is encrypted at rest |
| **Versioning** | S3 versioning enables state recovery |

### Bootstrap Process

The state infrastructure is automatically created by the CI/CD pipeline:

1. Pipeline checks if state bucket exists
2. If missing, runs `terraform-state/` to create:
   - S3 bucket with versioning and encryption
   - DynamoDB table for state locking
3. Imports any existing resources to handle partial states

## Resources Created

### AWS Free Tier Optimized

| Resource | Service | Free Tier Limit |
|----------|---------|-----------------|
| Raw Data Bucket | S3 | 5GB storage |
| Processed Data Bucket | S3 | 5GB storage |
| Lambda Function | Lambda | 1M requests/month |
| Metadata Table | DynamoDB | 25 RCU, 25 WCU |
| Notifications Topic | SNS | 1M publishes/month |
| Lambda Logs | CloudWatch | 5GB ingestion |

### Lambda Configuration

The Lambda function uses the **AWS SDK Pandas Layer** to avoid package size limits:

```hcl
layers = [
  "arn:aws:lambda:${var.aws_region}:336392948345:layer:AWSSDKPandas-Python39:28"
]
```

This provides:
- pandas
- numpy
- pyarrow

Without bundling them in the deployment package (which would exceed 250MB).

## Deployment Modes

### 1. CI/CD Deployment (Harness)

The pipeline handles everything automatically:

```bash
# Pipeline steps:
# 1. Bootstrap state backend (if needed)
# 2. Import existing resources (idempotent)
# 3. Upload Lambda package to S3
# 4. Run terraform apply
```

### 2. Local Deployment

For local testing or manual deployment:

```bash
# First, bootstrap state backend
cd infrastructure/terraform-state
terraform init
terraform apply -var="aws_region=us-east-1"

# Get the bucket name from output
STATE_BUCKET=$(terraform output -raw state_bucket_name)
LOCK_TABLE=$(terraform output -raw lock_table_name)

# Then deploy main infrastructure
cd ../terraform

# Build Lambda package first
python scripts/build_lambda.py

# Initialize with backend config
terraform init \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="dynamodb_table=${LOCK_TABLE}"

# Deploy
terraform apply -var="environment=dev" -var="aws_region=us-east-1"
```

## Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `environment` | Environment name (dev, staging, prod) | `dev` |
| `aws_region` | AWS region | `us-east-1` |
| `lambda_s3_key` | S3 key for Lambda ZIP (CI/CD mode) | `""` |
| `lambda_timeout` | Lambda timeout in seconds | `300` |
| `log_retention_days` | CloudWatch log retention | `7` |
| `enable_schedule` | Enable EventBridge schedule | `false` |
| `enable_alarms` | Enable CloudWatch alarms | `false` |

See [variables.tf](variables.tf) for full list.

## Idempotent Deployments

The CI/CD pipeline is designed to be **idempotent** - it works whether resources exist or not:

### Import Logic

Before `terraform apply`, the pipeline imports existing resources:

```bash
# Check if resource exists, then import
aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null && \
  terraform import aws_s3_bucket.raw_data "${BUCKET}" || true
```

This handles:
- Fresh deployments (no resources exist)
- Re-deployments (resources already in state)
- Recovery (resources exist but state is lost)

### Resources Imported

- S3 buckets (raw, processed)
- S3 lifecycle configurations
- S3 bucket notifications
- DynamoDB table
- IAM role and policy
- Lambda function
- Lambda permissions
- SNS topic
- CloudWatch log group

## Outputs

After deployment, these outputs are available:

```bash
terraform output

# Example outputs:
raw_data_bucket_name = "etl-pipeline-dev-raw-data-123456789"
processed_data_bucket_name = "etl-pipeline-dev-processed-data-123456789"
lambda_function_name = "etl-pipeline-dev-processor"
lambda_function_arn = "arn:aws:lambda:us-east-1:123456789:function:etl-pipeline-dev-processor"
dynamodb_table_name = "etl-pipeline-dev-metadata"
sns_topic_arn = "arn:aws:sns:us-east-1:123456789:etl-pipeline-dev-notifications"
```

## Destroying Resources

To tear down all infrastructure:

```bash
cd infrastructure/terraform

# Destroy main infrastructure
terraform destroy -var="environment=dev" -var="aws_region=us-east-1"

# Optionally destroy state backend (careful!)
cd ../terraform-state
terraform destroy -var="aws_region=us-east-1"
```

> **Warning**: Destroying the state backend will delete all state history.

## Troubleshooting

### "BucketAlreadyExists" Error

Resource exists but not in Terraform state. The pipeline handles this with imports, but for manual runs:

```bash
terraform import aws_s3_bucket.raw_data "etl-pipeline-dev-raw-data-123456789"
```

### "Resource already exists" on Lambda Permission

```bash
terraform import aws_lambda_permission.s3_trigger "etl-pipeline-dev-processor/AllowS3Invoke"
```

### State Lock Error

If a previous run crashed and left a lock:

```bash
terraform force-unlock LOCK_ID
```

### Provider Crash with Invalid Credentials

Ensure AWS credentials are exactly:
- Access Key ID: 20 characters
- Secret Access Key: 40 characters

Extra characters (spaces, newlines) will cause the AWS provider to crash.

## Related Documentation

- [Main README](../../README.md) - Project overview
- [Harness Setup](../../docs/harness_setup.md) - CI/CD pipeline details
- [ETL Documentation](../../etl/README.md) - Lambda function details
