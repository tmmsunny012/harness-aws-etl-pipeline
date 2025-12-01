# =============================================================================
# Terraform Variables
# =============================================================================

# -----------------------------------------------------------------------------
# General Settings
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "etl-pipeline"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# -----------------------------------------------------------------------------
# S3 Settings
# -----------------------------------------------------------------------------

variable "force_destroy_buckets" {
  description = "Allow destruction of S3 buckets with objects"
  type        = bool
  default     = true  # Set to true for easy cleanup during testing
}

variable "raw_data_retention_days" {
  description = "Days to retain raw data before deletion"
  type        = number
  default     = 30
}

variable "processed_data_retention_days" {
  description = "Days to retain processed data before deletion"
  type        = number
  default     = 90
}

# -----------------------------------------------------------------------------
# DynamoDB Settings
# -----------------------------------------------------------------------------

variable "dynamodb_read_capacity" {
  description = "DynamoDB read capacity units (Free Tier: 25 RCU)"
  type        = number
  default     = 5
}

variable "dynamodb_write_capacity" {
  description = "DynamoDB write capacity units (Free Tier: 25 WCU)"
  type        = number
  default     = 5
}

# -----------------------------------------------------------------------------
# Lambda Settings
# -----------------------------------------------------------------------------

variable "lambda_s3_key" {
  description = "S3 key for Lambda deployment package (for CI/CD). If empty, uses local build."
  type        = string
  default     = ""
}

variable "lambda_runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.9"
}

variable "lambda_memory" {
  description = "Lambda memory in MB (Free Tier: 128MB optimal for cost)"
  type        = number
  default     = 128  # 128MB = optimal for free tier (more GB-seconds per request)
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

# -----------------------------------------------------------------------------
# Logging Settings
# -----------------------------------------------------------------------------

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7  # Minimize costs
}

# -----------------------------------------------------------------------------
# Scheduling Settings
# -----------------------------------------------------------------------------

variable "enable_schedule" {
  description = "Enable scheduled ETL execution"
  type        = bool
  default     = false  # Disabled by default to save costs
}

variable "schedule_expression" {
  description = "EventBridge schedule expression"
  type        = string
  default     = "rate(1 hour)"
}

# -----------------------------------------------------------------------------
# Notification Settings
# -----------------------------------------------------------------------------

variable "notification_email" {
  description = "Email for SNS notifications (leave empty to skip)"
  type        = string
  default     = ""
}

variable "error_threshold" {
  description = "Number of errors before alarm triggers"
  type        = number
  default     = 3
}

# -----------------------------------------------------------------------------
# Monitoring Settings (Free Tier: 10 alarms)
# -----------------------------------------------------------------------------

variable "enable_alarms" {
  description = "Enable CloudWatch alarms (Free Tier: 10 alarms max)"
  type        = bool
  default     = false  # Disabled by default to stay within free tier
}
