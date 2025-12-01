# AWS ETL Pipeline with Harness CI/CD

A serverless ETL (Extract, Transform, Load) pipeline deployed on AWS using Terraform and Harness CI/CD. Optimized for AWS Free Tier.

## Overview

This project implements a production-ready ETL pipeline that:
- Extracts data from S3 (CSV, JSON, Parquet)
- Transforms data using pandas (cleaning, validation, enrichment)
- Loads processed data to S3 in Parquet format
- Tracks job metadata in DynamoDB
- Sends notifications via SNS

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   S3 Raw     │────>│   Lambda    │────>│ S3 Processed │
│  (incoming)  │     │ (ETL Logic) │     │  (parquet)   │
└──────────────┘     └──────┬──────┘     └──────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
               ┌────▼────┐  ┌─────▼─────┐
               │DynamoDB │  │    SNS    │
               │(metadata)│ │(alerts)   │
               └─────────┘  └───────────┘
```

## Quick Start

### Option 1: Deploy with Harness CI/CD (Recommended)

The easiest way to deploy - uses Harness for automated CI/CD:

1. **Fork/Clone the repository**
   ```bash
   git clone https://github.com/tmmsunny012/harness-aws-etl-pipeline.git
   cd harness-aws-etl-pipeline
   ```

2. **Set up Harness** - Follow [docs/harness_setup.md](docs/harness_setup.md)
   - Create Harness account (free tier)
   - Configure AWS connector with secrets
   - Import pipeline from `.harness/pipeline.yaml`

3. **Run the pipeline**
   - Go to Harness > Pipelines > ETL Pipeline Deployment
   - Click **Run** and select environment (dev/staging/prod)
   - Pipeline will automatically:
     - Run tests
     - Build Lambda package
     - Create/update all AWS resources
     - Verify deployment

### Option 2: Deploy Manually with Terraform

For local development or manual deployment:

1. **Prerequisites**
   ```bash
   # Install required tools
   - Python 3.9+
   - Terraform >= 1.0 (or OpenTofu)
   - AWS CLI v2
   ```

2. **Configure AWS credentials**
   ```bash
   aws configure
   # AWS Access Key ID: <your-access-key>
   # AWS Secret Access Key: <your-secret-key>
   # Default region name: us-east-1
   ```

3. **Build Lambda package**
   ```bash
   python scripts/build_lambda.py
   ```

4. **Bootstrap Terraform state backend**
   ```bash
   cd infrastructure/terraform-state
   terraform init
   terraform apply -var="aws_region=us-east-1"

   # Note the output values for next step
   ```

5. **Deploy infrastructure**
   ```bash
   cd ../terraform

   # Initialize with S3 backend
   terraform init \
     -backend-config="bucket=etl-pipeline-terraform-state-<ACCOUNT_ID>" \
     -backend-config="dynamodb_table=etl-pipeline-terraform-locks"

   # Deploy
   terraform apply -var="environment=dev" -var="aws_region=us-east-1"
   ```

### Option 3: Local Development with LocalStack

Test the ETL pipeline locally without AWS costs:

```bash
# Start LocalStack
docker-compose up -d localstack

# Run ETL locally
python scripts/run_local.py --full-test

# Run tests
pytest tests/ -v
```

## Project Structure

```
harness-aws-etl-pipeline/
├── .harness/
│   └── pipeline.yaml           # Harness CI/CD pipeline definition
│
├── etl/                        # ETL application code
│   ├── lambda_handler.py       # Lambda entry point
│   ├── requirements-lambda.txt # Lambda dependencies (lightweight)
│   ├── README.md               # ETL technical documentation
│   └── src/
│       ├── extract/            # Data extraction from S3
│       ├── transform/          # Data transformation logic
│       ├── load/               # Data loading to S3
│       └── utils/              # AWS clients, config, metadata
│
├── infrastructure/
│   ├── terraform/              # Main infrastructure
│   │   ├── main.tf             # AWS resources (Lambda, S3, DynamoDB, etc.)
│   │   ├── variables.tf        # Configuration variables
│   │   ├── outputs.tf          # Output values
│   │   └── README.md           # Terraform documentation
│   │
│   └── terraform-state/        # State backend bootstrap
│       └── main.tf             # S3 bucket + DynamoDB for state
│
├── tests/
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests (LocalStack)
│
├── scripts/
│   ├── build_lambda.py         # Build Lambda deployment package
│   └── run_local.py            # Local development runner
│
└── docs/
    ├── SETUP.md                # Detailed setup guide
    └── harness_setup.md        # Harness CI/CD configuration
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/harness_setup.md](docs/harness_setup.md) | Harness CI/CD setup and pipeline execution details |
| [docs/SETUP.md](docs/SETUP.md) | Complete setup guide with AWS IAM permissions |
| [infrastructure/terraform/README.md](infrastructure/terraform/README.md) | Terraform configuration and state management |
| [etl/README.md](etl/README.md) | ETL technical documentation, AWS services deep dive |

## AWS Resources Created

All resources are optimized for AWS Free Tier:

| Resource | Service | Free Tier Limit |
|----------|---------|-----------------|
| Raw Data Bucket | S3 | 5GB storage |
| Processed Data Bucket | S3 | 5GB storage |
| ETL Processor | Lambda | 1M requests/month |
| Metadata Table | DynamoDB | 25 RCU, 25 WCU |
| Notifications | SNS | 1M publishes/month |
| Logs | CloudWatch | 5GB ingestion |

## Key Features

### Idempotent Deployments

The CI/CD pipeline works whether resources exist or not:
- Imports existing resources into Terraform state
- Creates missing resources
- Handles recovery from partial failures

### AWS Lambda Layer for Dependencies

Heavy dependencies (pandas, numpy, pyarrow) are provided by AWS Lambda Layer:
```hcl
layers = [
  "arn:aws:lambda:${region}:336392948345:layer:AWSSDKPandas-Python39:28"
]
```
This keeps deployment package under 10MB (vs 300MB+ without layer).

### Remote State Management

Terraform state is stored in S3 with DynamoDB locking:
- State persists across CI/CD runs
- Prevents concurrent modifications
- Enables state recovery via S3 versioning

## Usage

### Trigger ETL Processing

**Automatic (S3 Event):**
Upload a file to the raw data bucket:
```bash
aws s3 cp data/sample.csv s3://etl-pipeline-dev-raw-data-<ACCOUNT_ID>/incoming/
```

**Manual Invocation:**
```bash
aws lambda invoke \
  --function-name etl-pipeline-dev-processor \
  --payload '{"source_bucket": "etl-pipeline-dev-raw-data-<ACCOUNT_ID>", "source_key": "incoming/sample.csv"}' \
  response.json
```

### View Results

```bash
# Check processed data
aws s3 ls s3://etl-pipeline-dev-processed-data-<ACCOUNT_ID>/processed/ --recursive

# Check job metadata
aws dynamodb scan --table-name etl-pipeline-dev-metadata

# View Lambda logs
aws logs tail /aws/lambda/etl-pipeline-dev-processor --since 30m
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `environment` | Target environment (dev, staging, prod) | dev |
| `aws_region` | AWS region for deployment | us-east-1 |

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "BucketAlreadyExists" | Pipeline imports existing resources - this is handled automatically |
| Lambda package too large | Dependencies provided by Lambda Layer, not bundled |
| Terraform state lost | State stored in S3, recoverable via imports |
| AWS provider crash | Using OpenTofu instead of Terraform to avoid credential parsing bugs |

### Debug Commands

```bash
# Check Lambda function
aws lambda get-function --function-name etl-pipeline-dev-processor

# View recent errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/etl-pipeline-dev-processor \
  --filter-pattern "ERROR"

# Check Terraform state
cd infrastructure/terraform
terraform state list
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Submit a pull request

## License

MIT License

## Support

- GitHub Issues: Report bugs and feature requests
- Documentation: Check the `/docs` folder
