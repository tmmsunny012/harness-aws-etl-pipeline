# ETL Pipeline Setup Guide

This guide walks you through setting up and deploying the AWS ETL Pipeline.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [AWS Configuration](#aws-configuration)
4. [Harness CI/CD Setup](#harness-cicd-setup)
5. [Deployment](#deployment)
6. [Running Lambda on AWS](#running-lambda-on-aws)
7. [Testing & Viewing Outputs](#testing--viewing-outputs)
8. [Shutdown & Cleanup](#shutdown--cleanup)

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.9+ | ETL application |
| Docker | 20.10+ | Local testing |
| Docker Compose | 2.0+ | Local orchestration |
| Terraform | 1.0+ | Infrastructure deployment |
| AWS CLI | 2.0+ | AWS interaction |
| Git | 2.0+ | Version control |

### Installation Commands

---

#### Windows Installation

**Option A: Using winget (Recommended - No Admin Required)**
```powershell
# Python
winget install Python.Python.3.11

# Docker Desktop
winget install Docker.DockerDesktop

# Terraform
winget install Hashicorp.Terraform

# AWS CLI
winget install Amazon.AWSCLI

# Git
winget install Git.Git
```

**Option B: Using Chocolatey (Requires Admin)**
```powershell
# Open PowerShell as Administrator, then run:
choco install python docker-desktop terraform awscli git
```

**Option C: Manual Installation (No Admin Required)**

1. **Python**: Download from https://www.python.org/downloads/
   - Check "Add Python to PATH" during installation

2. **Docker Desktop**: Download from https://www.docker.com/products/docker-desktop/

3. **Terraform**:
   ```powershell
   # Download and extract to a folder in your PATH
   # Or use the installer from https://developer.hashicorp.com/terraform/downloads

   # Manual method:
   mkdir C:\tools
   cd C:\tools
   Invoke-WebRequest -Uri "https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_windows_amd64.zip" -OutFile "terraform.zip"
   Expand-Archive -Path "terraform.zip" -DestinationPath "."

   # Add to PATH (run in elevated PowerShell or add manually via System Properties)
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\tools", "User")
   ```

4. **AWS CLI**: Download installer from https://aws.amazon.com/cli/

5. **Git**: Download from https://git-scm.com/download/win

**Verify Installation (Windows)**
```powershell
python --version
docker --version
terraform --version
aws --version
git --version
```

---

#### macOS Installation

**Using Homebrew (Recommended)**
```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install all tools
brew install python@3.11 terraform awscli git
brew install --cask docker
```

**Verify Installation (macOS)**
```bash
python3 --version
docker --version
terraform --version
aws --version
git --version
```

---

#### Linux (Ubuntu/Debian) Installation

```bash
# Update package list
sudo apt-get update

# Python
sudo apt-get install -y python3.11 python3-pip python3-venv

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect

# Terraform
sudo apt-get install -y gnupg software-properties-common
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install -y terraform

# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws/

# Git
sudo apt-get install -y git
```

---

#### Linux (CentOS/RHEL/Fedora) Installation

```bash
# Python
sudo dnf install -y python3.11 python3-pip

# Docker
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

# Terraform
sudo dnf install -y yum-utils
sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
sudo dnf install -y terraform

# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws/

# Git
sudo dnf install -y git
```

---

#### Verify All Installations

```bash
# Run these commands to verify everything is installed
python3 --version    # Should show Python 3.9+
docker --version     # Should show Docker 20.10+
terraform --version  # Should show Terraform 1.0+
aws --version        # Should show AWS CLI 2.x
git --version        # Should show Git 2.x
```

---

## Local Development Setup

### Step 1: Clone Repository

```bash
git clone <your-repo-url>
cd harness_ci_cd_aws
```

### Step 2: Create Virtual Environment

**Windows (Command Prompt)**
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If you get an execution policy error, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Windows (Git Bash / MINGW)**
```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
```

**macOS**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Linux**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Deactivate (All Platforms)**
```bash
deactivate
```

### Step 3: Start Local Services

```bash
# Start LocalStack (AWS emulator)
docker-compose up -d localstack

# Wait for LocalStack to be ready (about 30 seconds)
# Check health:
curl http://localhost:4566/_localstack/health
```

### Step 4: Initialize Local Resources

```bash
# Initialize S3 buckets, DynamoDB, etc.
python scripts/run_local.py --init --upload-sample
```

### Step 5: Run Local Tests

```bash
# Run all tests
make test

# Run only unit tests
make test-unit

# Run integration tests (requires LocalStack)
make test-integration

# Run with coverage
make coverage
```

### Step 6: Test ETL Pipeline Locally

```bash
# Run the full ETL pipeline against LocalStack
python scripts/run_local.py --full-test
```

---

## AWS Configuration

### Step 1: Create AWS Account (if needed)

1. Go to https://aws.amazon.com
2. Click "Create an AWS Account"
3. Follow the registration process
4. Enable MFA for security

### Step 2: Create IAM User

1. Go to AWS Console → IAM → Users
2. Click "Create user"
3. User name: `etl-pipeline-deployer`
4. Select "Provide user access to the AWS Management Console" (optional)
5. Click "Attach policies directly" and add these AWS managed policies:

| Policy Name | ARN | Purpose |
|-------------|-----|---------|
| `AmazonS3FullAccess` | `arn:aws:iam::aws:policy/AmazonS3FullAccess` | S3 bucket operations |
| `AmazonDynamoDBFullAccess` | `arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess` | DynamoDB table operations |
| `AWSLambda_FullAccess` | `arn:aws:iam::aws:policy/AWSLambda_FullAccess` | Lambda function deployment |
| `AmazonSNSFullAccess` | `arn:aws:iam::aws:policy/AmazonSNSFullAccess` | SNS notifications |
| `AmazonEventBridgeFullAccess` | `arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess` | EventBridge scheduling |
| `CloudWatchLogsFullAccess` | `arn:aws:iam::aws:policy/CloudWatchLogsFullAccess` | CloudWatch logging |
| `IAMFullAccess` | `arn:aws:iam::aws:policy/IAMFullAccess` | Create IAM roles for Lambda |
| `AmazonEC2ReadOnlyAccess` | `arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess` | **Required for Harness connector** |

6. Click "Create user"
7. Go to the user → Security credentials → Create access key
8. Select "Command Line Interface (CLI)" and download the credentials CSV

#### Why EC2 Read Access?

Harness requires `ec2:DescribeRegions` permission to validate AWS connectors. This permission is mandatory for **all** AWS connectors regardless of the AWS services you're using. The `AmazonEC2ReadOnlyAccess` managed policy includes this permission.

**Alternative: Minimal Custom Policy for Harness**

If you prefer minimal permissions, create a custom inline policy instead of `AmazonEC2ReadOnlyAccess`:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "HarnessConnectorValidation",
            "Effect": "Allow",
            "Action": "ec2:DescribeRegions",
            "Resource": "*"
        }
    ]
}
```

To add this custom policy:
1. Go to IAM → Users → `etl-pipeline-deployer`
2. Click **Add permissions** → **Create inline policy**
3. Select **JSON** tab and paste the above policy
4. Name it: `harness-connector-validation`
5. Click **Create policy**

### Step 3: Configure AWS CLI

```bash
aws configure
# AWS Access Key ID: <your-access-key>
# AWS Secret Access Key: <your-secret-key>
# Default region name: us-east-1
# Default output format: json
```

### Step 4: Verify Configuration

```bash
# Check credentials
aws sts get-caller-identity

# Should output:
# {
#     "UserId": "AIDAXXXXXXXXXX",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/etl-pipeline-deployer"
# }
```

### Step 5: Create Local Config File

```bash
# Copy template
cp config/aws_config.template config/aws_config.env

# Edit with your credentials
# NEVER commit this file to git!
```

---

## Harness CI/CD Setup

### Step 1: Create Harness Account

1. Go to https://app.harness.io
2. Sign up for free account
3. Create a new project

### Step 2: Connect GitHub Repository

1. In Harness, go to **Project Settings** → **Connectors**
2. Click **New Connector** → **Code Repository** → **GitHub**
3. Configure:
   - Name: `github-etl-pipeline`
   - URL: Your repository URL
   - Authentication: Personal Access Token or OAuth
4. Test connection and save

### Step 3: Add AWS Connector

1. Go to **Project Settings** → **Connectors**
2. Click **New Connector** → **Cloud Providers** → **AWS**
3. Configure:
   - Name: `aws-etl-deployment`
   - Credentials: Manual (Access Key + Secret Key)
   - Or: Use IAM Role (if running in AWS)
4. Test connection and save

### Step 4: Add Secrets

1. Go to **Project Settings** → **Secrets**
2. Add the following secrets:
   - `aws_access_key`: Your AWS Access Key
   - `aws_secret_key`: Your AWS Secret Key

### Step 5: Import Pipeline

1. Go to **Pipelines** → **Create Pipeline**
2. Select **Import from Git**
3. Choose your GitHub connector
4. Path: `.harness/pipeline.yaml`
5. Click **Import**

### Step 6: Configure GitHub Actions (Optional)

Add these secrets to your GitHub repository:
- `HARNESS_API_KEY`: Your Harness API key
- `HARNESS_ACCOUNT_ID`: Your Harness account ID
- `HARNESS_ORG_ID`: Your organization ID
- `HARNESS_PROJECT_ID`: Your project ID

---

## Deployment

### Pre-Deployment: Build Lambda Package

**IMPORTANT:** Before deploying, you must build the Lambda package with dependencies:

```bash
# Build the Lambda deployment package (includes pandas, numpy, etc.)
python scripts/build_lambda.py
```

This creates `build/lambda_function.zip` (~82MB) containing:
- Lambda handler code
- ETL modules (extract, transform, load)
- Python dependencies (pandas, numpy, pyarrow, boto3)

### Option 1: Manual Deployment with Terraform

```bash
# Build Lambda package first (required!)
python scripts/build_lambda.py

# Navigate to Terraform directory
cd infrastructure/terraform

# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Deploy
terraform apply

# Note the outputs
terraform output
```

### Option 2: Deploy with Script

```bash
# Deploy to dev
./infrastructure/scripts/deploy.sh dev

# Deploy to staging
./infrastructure/scripts/deploy.sh staging

# Deploy to production (requires confirmation)
./infrastructure/scripts/deploy.sh prod
```

### Option 3: Deploy via Harness

1. Go to Harness → Pipelines
2. Select "ETL Pipeline Deployment"
3. Click "Run"
4. Select input set (dev/staging/prod)
5. Click "Run Pipeline"

### Post-Deployment Verification

```bash
# Check resource status
python scripts/status_check.py --environment dev

# Upload test data
aws s3 cp sample_data/sample_sales.csv s3://<raw-bucket>/incoming/

# Check Lambda logs
aws logs tail /aws/lambda/etl-pipeline-dev-processor --follow
```

---

## Running Lambda on AWS

After deploying with Terraform and uploading data to S3, here's how to run and test the Lambda function.

### Option 1: Automatic Trigger (S3 Event)

The Lambda is automatically triggered when you upload files to the raw data bucket:

```bash
# Upload a file - Lambda triggers automatically
aws s3 cp sample_data/sample_sales.csv s3://etl-pipeline-dev-raw-data-<account-id>/incoming/

# Replace <account-id> with your AWS account ID
# Find your account ID with:
aws sts get-caller-identity --query Account --output text
```

### Option 2: Manual Invocation

Invoke the Lambda directly with a custom payload:

```bash
# Invoke Lambda with test payload
aws lambda invoke \
  --function-name etl-pipeline-dev-processor \
  --payload '{"source_bucket": "etl-pipeline-dev-raw-data-<account-id>", "source_key": "incoming/sample_sales.csv"}' \
  --cli-binary-format raw-in-base64-out \
  output.json

# View the response
cat output.json
```

**Windows PowerShell:**
```powershell
aws lambda invoke `
  --function-name etl-pipeline-dev-processor `
  --payload '{\"source_bucket\": \"etl-pipeline-dev-raw-data-<account-id>\", \"source_key\": \"incoming/sample_sales.csv\"}' `
  --cli-binary-format raw-in-base64-out `
  output.json

Get-Content output.json
```

---

## Testing & Viewing Outputs

### 1. Check Lambda Execution Logs

```bash
# View recent logs (follow mode)
aws logs tail /aws/lambda/etl-pipeline-dev-processor --follow

# View last 30 minutes of logs
aws logs tail /aws/lambda/etl-pipeline-dev-processor --since 30m

# Search for specific job
aws logs filter-log-events \
  --log-group-name /aws/lambda/etl-pipeline-dev-processor \
  --filter-pattern "etl-"
```

### 2. Check Processed Data in S3

```bash
# List processed files
aws s3 ls s3://etl-pipeline-dev-processed-data-<account-id>/ --recursive

# Download processed file to inspect
aws s3 cp s3://etl-pipeline-dev-processed-data-<account-id>/processed/<filename>.parquet ./output/

# List archive bucket
aws s3 ls s3://etl-pipeline-dev-archive-<account-id>/ --recursive
```

### 3. Check Job Metadata in DynamoDB

```bash
# List all jobs
aws dynamodb scan \
  --table-name etl-pipeline-dev-metadata \
  --output table

# Query specific job
aws dynamodb query \
  --table-name etl-pipeline-dev-metadata \
  --key-condition-expression "job_id = :jid" \
  --expression-attribute-values '{":jid": {"S": "etl-20241130-123456"}}' \
  --output table
```

### 4. Check SNS Notifications

```bash
# List SNS topics
aws sns list-topics

# Get topic ARN and check subscriptions
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:<account-id>:etl-pipeline-dev-notifications
```

### 5. Quick Status Check Script

Run this to get a full status overview:

```bash
# Get account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ENV="dev"

echo "=== S3 Buckets ==="
echo "Raw data:"
aws s3 ls s3://etl-pipeline-${ENV}-raw-data-${ACCOUNT_ID}/ --recursive --human-readable
echo ""
echo "Processed data:"
aws s3 ls s3://etl-pipeline-${ENV}-processed-data-${ACCOUNT_ID}/ --recursive --human-readable

echo ""
echo "=== Recent Lambda Invocations ==="
aws logs tail /aws/lambda/etl-pipeline-${ENV}-processor --since 1h --format short

echo ""
echo "=== DynamoDB Job Records ==="
aws dynamodb scan --table-name etl-pipeline-${ENV}-metadata --output table
```

**Windows PowerShell version:**
```powershell
$ACCOUNT_ID = aws sts get-caller-identity --query Account --output text
$ENV = "dev"

Write-Host "=== S3 Buckets ===" -ForegroundColor Cyan
Write-Host "Raw data:"
aws s3 ls "s3://etl-pipeline-$ENV-raw-data-$ACCOUNT_ID/" --recursive --human-readable

Write-Host "`nProcessed data:"
aws s3 ls "s3://etl-pipeline-$ENV-processed-data-$ACCOUNT_ID/" --recursive --human-readable

Write-Host "`n=== Recent Lambda Invocations ===" -ForegroundColor Cyan
aws logs tail "/aws/lambda/etl-pipeline-$ENV-processor" --since 1h --format short

Write-Host "`n=== DynamoDB Job Records ===" -ForegroundColor Cyan
aws dynamodb scan --table-name "etl-pipeline-$ENV-metadata" --output table
```

---

## Example: Full Test Workflow

Here's a complete test from upload to verification:

```bash
# 1. Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account ID: $ACCOUNT_ID"

# 2. Upload sample data
aws s3 cp sample_data/sample_sales.csv \
  s3://etl-pipeline-dev-raw-data-${ACCOUNT_ID}/incoming/test_$(date +%Y%m%d_%H%M%S).csv

# 3. Wait a few seconds for Lambda to process
echo "Waiting for Lambda to process..."
sleep 10

# 4. Check logs for the job
aws logs tail /aws/lambda/etl-pipeline-dev-processor --since 1m

# 5. Check processed output
aws s3 ls s3://etl-pipeline-dev-processed-data-${ACCOUNT_ID}/ --recursive

# 6. Check job metadata
aws dynamodb scan --table-name etl-pipeline-dev-metadata --output table
```

### Expected Output

After a successful run, you should see:

1. **In CloudWatch Logs:**
   ```
   Starting ETL job: etl-20241130-143052
   Processing source: {'type': 's3', 'bucket': '...', 'key': '...'}
   Starting EXTRACT phase...
   Extracted 100 rows
   Starting TRANSFORM phase...
   Transformed data: {'input_rows': 100, 'output_rows': 98, ...}
   Starting LOAD phase...
   Loaded data to: s3://etl-pipeline-dev-processed-data-.../processed/...
   ETL job completed successfully: etl-20241130-143052
   ```

2. **In Processed S3 Bucket:**
   - Parquet files in `processed/YYYY/MM/DD/` folders

3. **In DynamoDB:**
   - Job record with status "SUCCESS", timing, and statistics

---

## Shutdown & Cleanup

### ⚠️ IMPORTANT: Always shutdown resources after testing to avoid charges!

### Option 1: Terraform Destroy

```bash
cd infrastructure/terraform
terraform destroy
```

### Option 2: Shutdown Script

```bash
# Shutdown dev environment
./infrastructure/scripts/shutdown.sh dev

# Shutdown all environments
./infrastructure/scripts/shutdown.sh --all
```

### Option 3: Python Cleanup Script

```bash
# Dry run (see what would be deleted)
python scripts/cleanup.py --environment dev --dry-run

# Execute cleanup
python scripts/cleanup.py --environment dev --force

# Cleanup all environments
python scripts/cleanup.py --all --force
```

### Verify Cleanup

```bash
# Check no resources remain
python scripts/status_check.py --environment dev

# Should show no resources
```

---

## Troubleshooting

### LocalStack Not Starting

```bash
# Reset Docker
docker-compose down -v
docker system prune -f
docker-compose up -d
```

### AWS Credentials Error

```bash
# Verify credentials
aws sts get-caller-identity

# Reconfigure if needed
aws configure
```

### Terraform State Issues

```bash
# Refresh state
terraform refresh

# If state is corrupted
rm -rf .terraform terraform.tfstate*
terraform init
```

### Lambda Deployment Package Too Large

```bash
# Use Lambda layers for dependencies
# Or use container image deployment
```

---

## Free Tier Limits Reference

| Service | Free Tier Limit | Our Default Usage |
|---------|-----------------|-------------------|
| S3 | 5GB storage, 20K GET, 2K PUT | ~100MB |
| Lambda | 1M requests, 400K GB-sec | ~1000 requests |
| DynamoDB | 25 RCU, 25 WCU, 25GB | 5 RCU, 5 WCU |
| CloudWatch | 5GB logs | ~10MB |
| SNS | 1M publishes | ~100 |

---

## Support

- GitHub Issues: Report bugs and feature requests
- Documentation: Check the `/docs` folder
- AWS Support: https://aws.amazon.com/support
