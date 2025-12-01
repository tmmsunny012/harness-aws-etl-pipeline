# Harness CI/CD Setup Guide

Detailed instructions for setting up Harness CI/CD for the ETL Pipeline.

## Overview

This guide covers:
1. Creating a Harness account
2. Configuring connectors
3. Importing the pipeline
4. Setting up triggers
5. Managing deployments

---

## Step 1: Create Harness Account

### Sign Up for Free Tier

1. Visit https://app.harness.io/auth/#/signup
2. Choose "Sign up with Email" or SSO option
3. Complete registration
4. Verify your email

### Create a Project

1. After login, click **"New Project"**
2. Configure:
   - **Name**: `etl-pipeline`
   - **Organization**: Select or create
   - **Description**: "AWS ETL Pipeline CI/CD"
3. Click **Save**

---

## Step 2: Configure Connectors

### GitHub Connector

1. Navigate to **Project Settings** → **Connectors**
2. Click **+ New Connector**
3. Select **Code Repositories** → **GitHub**
4. Configure:

```yaml
Name: github-etl-repo
URL Type: Repository
Connection Type: HTTP
GitHub Repository URL: https://github.com/<your-org>/<your-repo>
Authentication:
  Type: Username and Token
  Username: <your-github-username>
  Personal Access Token: <create in GitHub Settings>
API Access: Enable API access (same credentials)
```

5. **Test Connection** → **Save**

### AWS Cloud Provider Connector

> **⚠️ IMPORTANT: IAM Permission Requirement**
>
> Harness requires `ec2:DescribeRegions` permission to validate ALL AWS connectors,
> regardless of which AWS services you're using. Ensure your IAM user has either:
> - `AmazonEC2ReadOnlyAccess` managed policy, OR
> - A custom policy with `ec2:DescribeRegions` action
>
> See [SETUP.md](./SETUP.md#step-2-create-iam-user) for details.

1. Click **+ New Connector**
2. Select **Cloud Providers** → **AWS**
3. **Overview** - Configure basic settings:

```yaml
Name: aws-deployment
Description: AWS connector for ETL pipeline deployment
```

4. **Credentials** - Choose connection method:

#### Option A: Connect through Harness Platform (Recommended)

Use this option to connect to AWS provider through the Harness Platform.
All credentials are encrypted and stored in the Harness Secret Manager.

```yaml
Connection Type: Connect through Harness Platform
Credential Type: AWS Access Key

Access Key ID: <your-aws-access-key>
  - Or reference a secret: <+secrets.getValue("aws_access_key")>

Secret Access Key: <reference to secret>
  - Click "Create or Select a Secret"
  - Create new: aws_secret_key
  - Value: Your AWS Secret Access Key
```

#### Option B: Connect through Harness Delegate

Use this option if you have a Harness Delegate running in your infrastructure
that has AWS access (via IAM role or instance profile).

```yaml
Connection Type: Connect through Harness Delegate
Credential Type:
  - Assume IAM Role on Delegate
  - Use IRSA (for EKS)
  - AWS Access Key
```

5. **AWS Backoff Strategy** (Optional but Recommended):

   If you encounter `ThrottlingException` or `Rate exceeded` errors for
   CloudFormation/ECS API calls, configure backoff strategy:

   | Strategy | Description | When to Use |
   |----------|-------------|-------------|
   | **Fixed Delay** | Always uses a fixed delay before retry | Simple, predictable workloads |
   | **Equal Jitter** | Uses equal jitter for computing retry delay | Moderate API call volume |
   | **Full Jitter** | Uses full jitter strategy for backoff delay | High API call volume (Recommended) |

   ```yaml
   AWS Backoff Strategy:
     Strategy Type: Full Jitter  # Recommended for most cases
     Base Delay: 1000ms
     Max Backoff Time: 30000ms
     Retry Count: 5
   ```

   > **Note**: These options are part of the AWS `software.amazon.awssdk.core.retry.backoff` package.

6. **Test Region**: Select a region for connection testing
   ```yaml
   Test Region: us-east-1
   ```

7. **Select Connectivity Mode**:
   - **Connect through Harness Platform**: Direct connection via Harness (no delegate needed)
   - **Connect through a Harness Delegate**: Use if delegate has network access to AWS

8. **Test Connection** → **Save**

#### Create Required Secrets First

Before configuring the connector, create these secrets:

1. Go to **Project Settings** → **Secrets** → **+ New Secret** → **Text**
2. Create:
   - **Name**: `aws_access_key`
   - **Value**: Your AWS Access Key ID

3. Create another:
   - **Name**: `aws_secret_key`
   - **Value**: Your AWS Secret Access Key

### Docker Registry Connector (Optional)

For Lambda container image deployments (instead of ZIP packages):

1. Click **+ New Connector**
2. Select **Artifact Repositories** → **Docker Registry**

#### Option A: Docker Hub

```yaml
Name: dockerhub-connector
Provider Type: DockerHub
Docker Registry URL: https://index.docker.io/v2/
Authentication: Username and Password
  Username: <your-dockerhub-username>
  Password: <create secret: dockerhub_password>
```

#### Option B: AWS ECR (Elastic Container Registry)

```yaml
Name: ecr-connector
Provider Type: Other (specify URL)
Docker Registry URL: https://<account-id>.dkr.ecr.<region>.amazonaws.com
Authentication: Anonymous (if using AWS connector for auth)
```

**Or use AWS Connector for ECR auth:**
1. Select **Artifact Repositories** → **Amazon Elastic Container Registry**
2. Configure:

```yaml
Name: ecr-etl-registry
Region: us-east-1
AWS Connector: aws-deployment (select the connector you created)
Registry ID: <your-aws-account-id>  # Optional, defaults to connector's account
```

3. **Test Connection** → **Save**

#### When to Use Docker Registry

| Deployment Type | Use Case |
|-----------------|----------|
| **ZIP Package** (Current setup) | Lambda functions < 250MB unzipped |
| **Container Image** | Lambda functions > 250MB, or custom runtimes |

> **Note**: This project uses ZIP deployment via S3. Container deployment is optional
> for future expansion if dependencies grow beyond Lambda's ZIP size limits.

---

## Step 3: Add Secrets

Navigate to **Project Settings** → **Secrets**

### Required Secrets

| Secret Name | Type | Description |
|-------------|------|-------------|
| `aws_access_key` | Text | AWS Access Key ID |
| `aws_secret_key` | Text | AWS Secret Access Key |
| `github_token` | Text | GitHub Personal Access Token |

### Creating a Secret

1. Click **+ New Secret** → **Text**
2. Enter:
   - **Name**: `aws_secret_key`
   - **Value**: Your secret value
   - **Description**: AWS Secret Access Key for deployment
3. Click **Save**

---

## Step 4: Import Pipeline

### From Git Repository

1. Navigate to **Pipelines**
2. Click **+ Create Pipeline**
3. Select **Import from Git**
4. Configure:

```yaml
Repository: github-etl-repo (your connector)
Git Branch: main
File Path: .harness/pipeline.yaml
```

5. Click **Import**

### Pipeline Structure

The imported pipeline has these stages:

```
1. Build and Test
   ├── Install dependencies (pip install)
   ├── Code linting (flake8)
   └── Unit tests (pytest)

2. Build and Deploy
   ├── Install tools (OpenTofu, AWS CLI)
   ├── Build Lambda package
   ├── Bootstrap state backend (if needed)
   ├── Import existing resources
   ├── Upload Lambda to S3
   └── Terraform apply

3. Verify Deployment
   ├── Check Lambda function
   ├── Check S3 buckets
   └── Check DynamoDB table
```

---

## Pipeline Execution Details

This section explains **what the pipeline does and why**.

### Stage 1: Build and Test

Validates code quality before deployment:

```yaml
steps:
  - pip install requirements.txt
  - flake8 etl/ --max-line-length=100
  - pytest tests/unit/ -v
```

### Stage 2: Build and Deploy

The main deployment stage with 8 steps:

#### Step 1: Install Tools

```bash
# OpenTofu (Terraform alternative - avoids AWS provider bugs)
curl -fsSL https://get.opentofu.org/install-opentofu.sh | sh
ln -s /usr/bin/tofu /usr/bin/terraform

# AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && ./aws/install
```

**Why OpenTofu?** The standard Terraform AWS provider has a bug that causes panics with certain credential formats. OpenTofu is a drop-in replacement that avoids this issue.

#### Step 2: Build Lambda Package

```bash
mkdir -p build/lambda_package
pip install -r etl/requirements-lambda.txt -t build/lambda_package/
cp -r etl/src/* build/lambda_package/
cp etl/lambda_handler.py build/lambda_package/
cd build/lambda_package && zip -r ../lambda_function.zip .
```

**Note:** Heavy dependencies (pandas, numpy, pyarrow) are NOT included - they're provided by AWS Lambda Layer.

#### Step 3: Setup Variables

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ENV="<+pipeline.variables.environment>"  # dev, staging, prod
REGION="<+pipeline.variables.aws_region>"  # us-east-1
STATE_BUCKET="etl-pipeline-terraform-state-${ACCOUNT_ID}"
```

#### Step 4: Bootstrap State Backend

```bash
# Check if state infrastructure exists
BUCKET_EXISTS=$(aws s3api head-bucket --bucket "${STATE_BUCKET}" 2>/dev/null && echo "yes" || echo "no")
TABLE_EXISTS=$(aws dynamodb describe-table --table-name "${LOCK_TABLE}" 2>/dev/null && echo "yes" || echo "no")

if [ "$BUCKET_EXISTS" = "no" ] || [ "$TABLE_EXISTS" = "no" ]; then
  cd infrastructure/terraform-state
  terraform init
  # Import existing resources if partial state
  terraform apply -auto-approve
fi
```

**Why?** Terraform needs a backend to store state. This creates the S3 bucket and DynamoDB table on first run.

#### Step 5: Terraform Init

```bash
terraform init -backend-config="bucket=${STATE_BUCKET}" \
               -backend-config="dynamodb_table=${LOCK_TABLE}"
```

#### Step 6: Import Existing Resources

```bash
# Import each resource if it exists (ignore errors)
aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null && \
  terraform import aws_s3_bucket.raw_data "${BUCKET}" || true

aws lambda get-function --function-name "${FUNC}" 2>/dev/null && \
  terraform import aws_lambda_function.etl_processor "${FUNC}" || true

# ... imports for all resources
```

**Why import?** This makes the pipeline **idempotent** - it works whether:
- Fresh deployment (imports fail silently)
- Re-deployment (resources already in state)
- Recovery (resources exist but state was lost)

#### Step 7: Upload Lambda to S3

```bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
S3_KEY="lambda-code/lambda_function-${TIMESTAMP}.zip"
aws s3 cp build/lambda_function.zip "s3://${PROCESSED_BUCKET}/${S3_KEY}"
```

#### Step 8: Terraform Apply

```bash
terraform apply -auto-approve \
  -var="environment=${ENV}" \
  -var="aws_region=${REGION}" \
  -var="lambda_s3_key=${S3_KEY}"
```

### Stage 3: Verify Deployment

Health checks to confirm deployment succeeded:

```bash
aws lambda get-function --function-name etl-pipeline-${ENV}-processor
aws s3 ls | grep etl-pipeline-${ENV}
aws dynamodb describe-table --table-name etl-pipeline-${ENV}-metadata
```

---

## Key Design Decisions

### 1. S3 Backend for Terraform State

| Problem | Solution |
|---------|----------|
| State lost between CI/CD runs | S3 bucket persists state |
| Concurrent runs corrupt state | DynamoDB locking |
| State recovery needed | S3 versioning enabled |

### 2. AWS Lambda Layer for Dependencies

| Problem | Solution |
|---------|----------|
| Package exceeds 250MB limit | Use AWS SDK Pandas Layer |
| pandas/numpy/pyarrow too large | Provided by layer, not bundled |

```hcl
layers = [
  "arn:aws:lambda:${region}:336392948345:layer:AWSSDKPandas-Python39:28"
]
```

### 3. Idempotent Resource Imports

| Problem | Solution |
|---------|----------|
| "Resource already exists" errors | Import before apply |
| Partial failures leave orphans | Import handles recovery |
| Multiple deploys to same env | Works every time |

### 4. OpenTofu Instead of Terraform

| Problem | Solution |
|---------|----------|
| AWS provider panic with credentials | OpenTofu avoids the bug |
| Same syntax and providers | Drop-in replacement |

---

## Step 5: Configure Input Sets

Input sets provide environment-specific variables.

### Import Dev Input Set

1. Go to **Pipelines** → Select your pipeline
2. Click **Input Sets** tab
3. Click **+ New Input Set** → **Import from Git**
4. File Path: `.harness/inputsets/dev.yaml`

### Import Prod Input Set

1. Repeat for `.harness/inputsets/prod.yaml`

### Using Input Sets

When running the pipeline:
1. Click **Run**
2. Select the appropriate Input Set
3. Or provide values manually

---

## Step 6: Set Up Triggers

### Git Webhook Trigger

1. Go to **Triggers** tab
2. Click **+ New Trigger**
3. Select **Webhook**
4. Configure:

```yaml
Name: github-push-trigger
Connector: github-etl-repo
Event: Push
Actions:
  - Create
  - Update

Conditions:
  Branch: main
  File Changes:
    - etl/**
    - infrastructure/**

Pipeline Input:
  environment: dev
  auto_approve: true
```

5. **Create Trigger**

### Scheduled Trigger (Optional)

For periodic deployments:

1. Click **+ New Trigger**
2. Select **Schedule**
3. Configure:

```yaml
Name: nightly-deploy
Schedule: 0 0 * * *  # Daily at midnight
Pipeline Input:
  environment: dev
```

---

## Step 7: Running the Pipeline

### Manual Run

1. Go to **Pipelines** → Select pipeline
2. Click **Run**
3. Choose:
   - **Use Input Set**: Select dev/staging/prod
   - **Provide Variables**: Fill in manually
4. Click **Run Pipeline**

### Monitor Execution

1. Watch real-time logs in each stage
2. View step-by-step execution
3. Check artifacts and outputs

### Approvals

For non-dev deployments:
1. Pipeline will pause at approval stage
2. Designated approvers receive notification
3. Review Terraform plan
4. Approve or reject

---

## Step 8: Post-Deployment

### Viewing Outputs

After successful deployment:
1. Go to completed pipeline execution
2. Check "Deploy Infrastructure" stage
3. View Terraform outputs in logs

### Accessing Resources

```bash
# Get deployment info from Harness outputs or:
aws s3 ls | grep etl-pipeline
aws lambda list-functions | grep etl-pipeline
aws dynamodb list-tables | grep etl-pipeline
```

---

## Pipeline Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `environment` | Target environment | dev |
| `aws_region` | AWS region | us-east-1 |
| `auto_approve` | Skip approval stage | false |

---

## Troubleshooting

### Connector Test Fails

**AWS Connector:**
- Verify access key is correct
- Check IAM permissions
- Ensure region is valid

**GitHub Connector:**
- Verify token has `repo` scope
- Check repository URL format
- Ensure token is not expired

### Pipeline Import Fails

- Check YAML syntax
- Verify file path is correct
- Ensure connector has repo access

### Terraform Fails

- Check AWS credentials in secrets
- Verify IAM permissions
- Review Terraform logs in Harness

### Approval Stage Issues

- Ensure user is in approved users list
- Check notification settings
- Verify user has pipeline execute permissions

---

## Best Practices

1. **Use Input Sets** for environment-specific configs
2. **Enable Approvals** for production deployments
3. **Set Up Notifications** for pipeline status
4. **Use Secrets** for all credentials
5. **Tag Resources** with pipeline execution ID
6. **Implement Rollback** strategies

---

## Additional Resources

- [Harness Documentation](https://developer.harness.io/docs)
- [Terraform Provider](https://registry.terraform.io/providers/hashicorp/aws)
- [AWS Free Tier](https://aws.amazon.com/free/)
