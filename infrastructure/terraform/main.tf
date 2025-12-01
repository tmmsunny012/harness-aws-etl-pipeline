# =============================================================================
# AWS ETL Pipeline Infrastructure - FREE TIER OPTIMIZED
# =============================================================================
# This Terraform configuration deploys a serverless ETL pipeline on AWS Free Tier
#
# FREE TIER LIMITS (as of 2024):
# - S3: 5GB storage, 20,000 GET, 2,000 PUT requests/month
# - Lambda: 1M requests, 400,000 GB-seconds/month
# - DynamoDB: 25 RCU, 25 WCU, 25GB storage
# - SNS: 1M publishes/month
# - CloudWatch: 10 alarms, 5GB logs ingestion
# - EventBridge: Free
#
# Resources created:
# - S3 buckets (raw, processed) - NO versioning to save storage
# - Lambda function for ETL processing
# - DynamoDB table for metadata (no GSI to save capacity)
# - SNS topic for notifications
# - CloudWatch log group (short retention)
# =============================================================================

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # S3 Backend for Remote State Storage
  # The bucket and table are created by infrastructure/terraform-state/
  # Backend config is passed via -backend-config in CI/CD pipeline
  backend "s3" {
    # These values are provided via -backend-config flags in the pipeline:
    # -backend-config="bucket=etl-pipeline-terraform-state-ACCOUNT_ID"
    # -backend-config="dynamodb_table=etl-pipeline-terraform-locks"
    key     = "etl-pipeline/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

# -----------------------------------------------------------------------------
# Provider Configuration
# -----------------------------------------------------------------------------
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      CostCenter  = "free-tier"
    }
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# Local Variables
# -----------------------------------------------------------------------------
locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# =============================================================================
# S3 BUCKETS (Free Tier: 5GB storage, 20K GET, 2K PUT)
# =============================================================================

# Raw Data Bucket - NO VERSIONING to stay within free tier
resource "aws_s3_bucket" "raw_data" {
  bucket        = "${local.name_prefix}-raw-data-${local.account_id}"
  force_destroy = var.force_destroy_buckets

  tags = merge(local.common_tags, {
    Name = "ETL Raw Data"
    Type = "raw"
  })
}

# Lifecycle rule to auto-delete old data (keeps storage under 5GB)
resource "aws_s3_bucket_lifecycle_configuration" "raw_data" {
  bucket = aws_s3_bucket.raw_data.id

  rule {
    id     = "expire-old-data"
    status = "Enabled"

    filter {}  # Apply to all objects

    expiration {
      days = var.raw_data_retention_days
    }
  }
}

# Processed Data Bucket - NO VERSIONING, NO TRANSITIONS to stay free
resource "aws_s3_bucket" "processed_data" {
  bucket        = "${local.name_prefix}-processed-data-${local.account_id}"
  force_destroy = var.force_destroy_buckets

  tags = merge(local.common_tags, {
    Name = "ETL Processed Data"
    Type = "processed"
  })
}

# Auto-delete processed data to stay within free tier
resource "aws_s3_bucket_lifecycle_configuration" "processed_data" {
  bucket = aws_s3_bucket.processed_data.id

  rule {
    id     = "expire-old-data"
    status = "Enabled"

    filter {}  # Apply to all objects

    # Delete after retention period - NO transition to IA (has min storage fees)
    expiration {
      days = var.processed_data_retention_days
    }
  }
}

# =============================================================================
# DYNAMODB TABLE (Free Tier: 25 RCU, 25 WCU, 25GB)
# =============================================================================

resource "aws_dynamodb_table" "metadata" {
  name           = "${local.name_prefix}-metadata"
  billing_mode   = "PROVISIONED"
  read_capacity  = var.dynamodb_read_capacity   # Default: 5 (within 25 free)
  write_capacity = var.dynamodb_write_capacity  # Default: 5 (within 25 free)
  hash_key       = "job_id"
  range_key      = "timestamp"

  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # NO Global Secondary Index - saves capacity units for free tier
  # If you need GSI, it would consume additional RCU/WCU

  # TTL enabled to auto-delete old items (keeps storage minimal)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "ETL Metadata"
  })
}

# =============================================================================
# SNS TOPIC (Free Tier: 1M publishes)
# =============================================================================

resource "aws_sns_topic" "notifications" {
  name = "${local.name_prefix}-notifications"

  tags = merge(local.common_tags, {
    Name = "ETL Notifications"
  })
}

# Optional: Email subscription (uncomment and set email)
# resource "aws_sns_topic_subscription" "email" {
#   count     = var.notification_email != "" ? 1 : 0
#   topic_arn = aws_sns_topic.notifications.arn
#   protocol  = "email"
#   endpoint  = var.notification_email
# }

# =============================================================================
# IAM ROLE FOR LAMBDA (Free - no charges for IAM)
# =============================================================================

resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${local.name_prefix}-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw_data.arn,
          "${aws_s3_bucket.raw_data.arn}/*",
          aws_s3_bucket.processed_data.arn,
          "${aws_s3_bucket.processed_data.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.metadata.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.notifications.arn
      }
    ]
  })
}

# =============================================================================
# LAMBDA FUNCTION (Free Tier: 1M requests, 400K GB-seconds)
# =============================================================================

# NOTE: Lambda package must be pre-built with dependencies using:
#   python scripts/build_lambda.py
#
# The package includes:
#   - lambda_handler.py (entry point)
#   - src/ (ETL modules)
#   - Dependencies (pandas, numpy, pyarrow, boto3, etc.)

# Lambda deployment supports two modes:
# 1. Local build: Upload from local build/ directory (for manual deployment)
# 2. CI/CD: Reference pre-uploaded S3 object (for Harness pipeline)

locals {
  # Use CI/CD S3 key if provided, otherwise use local build path
  use_cicd_deployment = var.lambda_s3_key != ""
  lambda_s3_key       = local.use_cicd_deployment ? var.lambda_s3_key : "lambda-code/lambda_function.zip"
}

# Upload Lambda code to S3 (only for local deployment)
resource "aws_s3_object" "lambda_code" {
  count  = local.use_cicd_deployment ? 0 : 1
  bucket = aws_s3_bucket.processed_data.id
  key    = "lambda-code/lambda_function.zip"
  source = "${path.module}/../../build/lambda_function.zip"
  etag   = filemd5("${path.module}/../../build/lambda_function.zip")
}

resource "aws_lambda_function" "etl_processor" {
  function_name = "${local.name_prefix}-processor"
  s3_bucket     = aws_s3_bucket.processed_data.id
  s3_key        = local.lambda_s3_key
  handler       = "lambda_handler.handler"
  runtime       = var.lambda_runtime
  role          = aws_iam_role.lambda_role.arn
  timeout       = var.lambda_timeout
  memory_size   = 256  # Increased for pandas/numpy memory requirements

  # Use AWS SDK Pandas Layer (includes pandas, numpy, pyarrow)
  # ARN format: arn:aws:lambda:<region>:336392948345:layer:AWSSDKPandas-Python39:28
  # See: https://aws-sdk-pandas.readthedocs.io/en/stable/layers.html
  layers = [
    "arn:aws:lambda:${var.aws_region}:336392948345:layer:AWSSDKPandas-Python39:28"
  ]

  # For CI/CD, we skip source_code_hash to allow updates via S3 key changes
  # For local, we use the file hash for change detection
  source_code_hash = local.use_cicd_deployment ? null : filebase64sha256("${path.module}/../../build/lambda_function.zip")

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      LOG_LEVEL           = var.log_level
      S3_RAW_BUCKET       = aws_s3_bucket.raw_data.id
      S3_PROCESSED_BUCKET = aws_s3_bucket.processed_data.id
      DYNAMODB_TABLE      = aws_dynamodb_table.metadata.name
      SNS_TOPIC_ARN       = aws_sns_topic.notifications.arn
    }
  }

  tags = merge(local.common_tags, {
    Name = "ETL Processor"
  })

  # Ensure S3 bucket exists before Lambda
  depends_on = [aws_s3_bucket.processed_data]
}

# =============================================================================
# CLOUDWATCH LOG GROUP (Free Tier: 5GB ingestion, 5GB storage)
# =============================================================================

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.etl_processor.function_name}"
  retention_in_days = var.log_retention_days  # Short retention saves storage

  tags = local.common_tags
}

# =============================================================================
# S3 EVENT TRIGGER (Free - no charges for S3 notifications)
# =============================================================================

resource "aws_lambda_permission" "s3_trigger" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.etl_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_data.arn
}

resource "aws_s3_bucket_notification" "raw_data_notification" {
  bucket = aws_s3_bucket.raw_data.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.etl_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
    filter_suffix       = ".csv"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.etl_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.s3_trigger]
}

# =============================================================================
# EVENTBRIDGE SCHEDULE (Free - Optional, disabled by default)
# =============================================================================

resource "aws_cloudwatch_event_rule" "schedule" {
  count               = var.enable_schedule ? 1 : 0
  name                = "${local.name_prefix}-schedule"
  description         = "Scheduled ETL execution"
  schedule_expression = var.schedule_expression

  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "lambda" {
  count     = var.enable_schedule ? 1 : 0
  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "ETLLambda"
  arn       = aws_lambda_function.etl_processor.arn

  input = jsonencode({
    source = "scheduled"
    time   = "scheduled-trigger"
  })
}

resource "aws_lambda_permission" "eventbridge" {
  count         = var.enable_schedule ? 1 : 0
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.etl_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}

# =============================================================================
# CLOUDWATCH ALARM - OPTIONAL (Free Tier: 10 alarms)
# Disabled by default - enable only if you need monitoring
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${local.name_prefix}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = var.error_threshold
  alarm_description   = "Lambda function errors"

  dimensions = {
    FunctionName = aws_lambda_function.etl_processor.function_name
  }

  alarm_actions = [aws_sns_topic.notifications.arn]

  tags = local.common_tags
}
