# =============================================================================
# Terraform Outputs
# =============================================================================

# -----------------------------------------------------------------------------
# S3 Buckets
# -----------------------------------------------------------------------------

output "raw_bucket_name" {
  description = "Name of the raw data S3 bucket"
  value       = aws_s3_bucket.raw_data.id
}

output "raw_bucket_arn" {
  description = "ARN of the raw data S3 bucket"
  value       = aws_s3_bucket.raw_data.arn
}

output "processed_bucket_name" {
  description = "Name of the processed data S3 bucket"
  value       = aws_s3_bucket.processed_data.id
}

output "processed_bucket_arn" {
  description = "ARN of the processed data S3 bucket"
  value       = aws_s3_bucket.processed_data.arn
}

# NOTE: Archive bucket removed to stay within Free Tier (only 2 buckets needed)

# -----------------------------------------------------------------------------
# DynamoDB
# -----------------------------------------------------------------------------

output "dynamodb_table_name" {
  description = "Name of the DynamoDB metadata table"
  value       = aws_dynamodb_table.metadata.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB metadata table"
  value       = aws_dynamodb_table.metadata.arn
}

# -----------------------------------------------------------------------------
# Lambda
# -----------------------------------------------------------------------------

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.etl_processor.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.etl_processor.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda IAM role"
  value       = aws_iam_role.lambda_role.arn
}

# -----------------------------------------------------------------------------
# SNS
# -----------------------------------------------------------------------------

output "sns_topic_arn" {
  description = "ARN of the SNS notification topic"
  value       = aws_sns_topic.notifications.arn
}

# -----------------------------------------------------------------------------
# CloudWatch
# -----------------------------------------------------------------------------

output "cloudwatch_log_group" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    environment    = var.environment
    region         = var.aws_region
    raw_bucket     = aws_s3_bucket.raw_data.id
    processed_bucket = aws_s3_bucket.processed_data.id
    lambda_function = aws_lambda_function.etl_processor.function_name
    dynamodb_table = aws_dynamodb_table.metadata.name
    sns_topic      = aws_sns_topic.notifications.name
  }
}

# -----------------------------------------------------------------------------
# Upload Instructions
# -----------------------------------------------------------------------------

output "upload_instructions" {
  description = "Instructions for uploading data"
  value = <<-EOT

    =====================================================
    ETL Pipeline Deployed Successfully!
    =====================================================

    To trigger the ETL pipeline, upload a CSV or JSON file:

    aws s3 cp your-data.csv s3://${aws_s3_bucket.raw_data.id}/incoming/

    To invoke Lambda manually:

    aws lambda invoke \
      --function-name ${aws_lambda_function.etl_processor.function_name} \
      --payload '{"source_bucket": "${aws_s3_bucket.raw_data.id}", "source_key": "your-file.csv"}' \
      response.json

    To view logs:

    aws logs tail /aws/lambda/${aws_lambda_function.etl_processor.function_name} --follow

    To SHUTDOWN all resources:

    terraform destroy -auto-approve

    =====================================================

  EOT
}
