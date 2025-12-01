#!/bin/bash
# =============================================================================
# AWS ETL Pipeline - Deployment Script
# =============================================================================
# Usage:
#   ./deploy.sh              # Deploy to dev
#   ./deploy.sh staging      # Deploy to staging
#   ./deploy.sh prod         # Deploy to prod (requires approval)
# =============================================================================

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=============================================="
echo "  ETL Pipeline Deployment"
echo "=============================================="
echo -e "${NC}"

echo -e "Environment: ${GREEN}${ENVIRONMENT}${NC}"
echo -e "Region:      ${GREEN}${REGION}${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v terraform &> /dev/null; then
    echo -e "${RED}Error: Terraform is not installed${NC}"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Verify AWS credentials
echo -e "${YELLOW}Verifying AWS credentials...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    echo "Please configure AWS credentials:"
    echo "  aws configure"
    echo "  or"
    echo "  export AWS_ACCESS_KEY_ID=your_key"
    echo "  export AWS_SECRET_ACCESS_KEY=your_secret"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "AWS Account: ${GREEN}${ACCOUNT_ID}${NC}"
echo ""

# Production safety check
if [ "$ENVIRONMENT" == "prod" ]; then
    echo -e "${RED}WARNING: You are about to deploy to PRODUCTION!${NC}"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Deployment cancelled."
        exit 0
    fi
fi

# Navigate to Terraform directory
cd "$TERRAFORM_DIR"

# Initialize Terraform
echo -e "${YELLOW}Initializing Terraform...${NC}"
terraform init -input=false

# Create/update terraform.tfvars
echo -e "${YELLOW}Configuring environment variables...${NC}"
cat > terraform.tfvars <<EOF
project_name = "etl-pipeline"
environment  = "${ENVIRONMENT}"
aws_region   = "${REGION}"
force_destroy_buckets = true
log_level    = "INFO"
EOF

# Plan deployment
echo -e "${YELLOW}Planning deployment...${NC}"
terraform plan -out=tfplan -input=false

# Show plan summary
echo ""
echo -e "${BLUE}=============================================="
echo "  Deployment Plan Summary"
echo -e "==============================================${NC}"
terraform show -no-color tfplan | grep -E "^(Plan:|  #)"
echo ""

# Confirm deployment (skip for dev with auto-approve)
if [ "$ENVIRONMENT" != "dev" ]; then
    read -p "Do you want to apply this plan? (yes/no): " apply_confirm
    if [ "$apply_confirm" != "yes" ]; then
        echo "Deployment cancelled."
        rm tfplan
        exit 0
    fi
fi

# Apply deployment
echo -e "${YELLOW}Applying deployment...${NC}"
terraform apply -auto-approve tfplan

# Cleanup plan file
rm -f tfplan

# Show outputs
echo ""
echo -e "${GREEN}=============================================="
echo "  Deployment Complete!"
echo -e "==============================================${NC}"
echo ""
terraform output deployment_summary
echo ""
terraform output upload_instructions

# Save deployment info
DEPLOYMENT_INFO="${SCRIPT_DIR}/../../.deployment-${ENVIRONMENT}.json"
terraform output -json > "$DEPLOYMENT_INFO"
echo -e "Deployment info saved to: ${BLUE}${DEPLOYMENT_INFO}${NC}"
