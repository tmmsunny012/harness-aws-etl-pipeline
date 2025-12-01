#!/bin/bash
# =============================================================================
# AWS ETL Pipeline - SHUTDOWN Script
# =============================================================================
# This script completely destroys all AWS resources to avoid charges.
#
# Usage:
#   ./shutdown.sh              # Shutdown dev environment
#   ./shutdown.sh staging      # Shutdown staging
#   ./shutdown.sh prod         # Shutdown prod (requires confirmation)
#   ./shutdown.sh --all        # Shutdown ALL environments
# =============================================================================

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}"
echo "=============================================="
echo "  ⚠️  AWS RESOURCE SHUTDOWN  ⚠️"
echo "=============================================="
echo -e "${NC}"

# Handle --all flag
if [ "$ENVIRONMENT" == "--all" ]; then
    echo -e "${RED}WARNING: This will destroy ALL environments!${NC}"
    echo ""
    echo "Environments to be destroyed:"
    echo "  - dev"
    echo "  - staging"
    echo "  - prod"
    echo ""
    read -p "Type 'DESTROY ALL' to confirm: " confirm
    if [ "$confirm" != "DESTROY ALL" ]; then
        echo "Shutdown cancelled."
        exit 0
    fi

    for env in dev staging prod; do
        echo ""
        echo -e "${YELLOW}Shutting down: ${env}${NC}"
        $0 "$env" --force || true
    done

    echo -e "${GREEN}All environments have been shut down.${NC}"
    exit 0
fi

echo -e "Environment: ${RED}${ENVIRONMENT}${NC}"
echo -e "Region:      ${RED}${REGION}${NC}"
echo ""

# Safety confirmation
if [ "$2" != "--force" ]; then
    echo -e "${RED}WARNING: This will permanently destroy all resources!${NC}"
    echo ""
    echo "Resources that will be deleted:"
    echo "  - S3 buckets (and all data)"
    echo "  - Lambda functions"
    echo "  - DynamoDB tables (and all data)"
    echo "  - SNS topics"
    echo "  - EventBridge rules"
    echo "  - CloudWatch log groups"
    echo "  - IAM roles"
    echo ""

    if [ "$ENVIRONMENT" == "prod" ]; then
        echo -e "${RED}⚠️  PRODUCTION ENVIRONMENT ⚠️${NC}"
        read -p "Type the environment name to confirm (prod): " env_confirm
        if [ "$env_confirm" != "prod" ]; then
            echo "Shutdown cancelled."
            exit 0
        fi
    fi

    read -p "Are you sure you want to shutdown ${ENVIRONMENT}? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Shutdown cancelled."
        exit 0
    fi
fi

# Navigate to Terraform directory
cd "$TERRAFORM_DIR"

# Check if Terraform state exists
if [ ! -f "terraform.tfstate" ] && [ ! -d ".terraform" ]; then
    echo -e "${YELLOW}No Terraform state found. Attempting cleanup with AWS CLI...${NC}"

    # Use Python cleanup script as fallback
    if [ -f "${SCRIPT_DIR}/../../scripts/cleanup.py" ]; then
        python "${SCRIPT_DIR}/../../scripts/cleanup.py" \
            --environment "$ENVIRONMENT" \
            --region "$REGION" \
            --force
    else
        echo -e "${RED}No cleanup method available.${NC}"
        echo "Please run: python scripts/cleanup.py --environment $ENVIRONMENT --force"
    fi
    exit 0
fi

# Initialize Terraform if needed
if [ ! -d ".terraform" ]; then
    echo -e "${YELLOW}Initializing Terraform...${NC}"
    terraform init -input=false
fi

# Set environment variables
cat > terraform.tfvars <<EOF
project_name = "etl-pipeline"
environment  = "${ENVIRONMENT}"
aws_region   = "${REGION}"
force_destroy_buckets = true
EOF

# Show what will be destroyed
echo -e "${YELLOW}Planning destruction...${NC}"
terraform plan -destroy -out=destroy.tfplan -input=false || true

echo ""
echo -e "${RED}=============================================="
echo "  Resources to be DESTROYED"
echo -e "==============================================${NC}"
terraform show -no-color destroy.tfplan 2>/dev/null | grep -E "will be destroyed" || echo "  (Unable to show plan details)"
echo ""

# Execute destruction
echo -e "${RED}Destroying resources...${NC}"
terraform destroy -auto-approve

# Cleanup
rm -f destroy.tfplan
rm -f terraform.tfvars

echo ""
echo -e "${GREEN}=============================================="
echo "  ✅ Shutdown Complete"
echo "=============================================="
echo -e "${NC}"
echo ""
echo "All resources for ${ENVIRONMENT} have been destroyed."
echo ""
echo "To verify, run:"
echo "  python scripts/status_check.py --environment ${ENVIRONMENT}"
echo ""
echo "To redeploy, run:"
echo "  ./infrastructure/scripts/deploy.sh ${ENVIRONMENT}"
