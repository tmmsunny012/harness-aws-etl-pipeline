.PHONY: help setup install test test-unit test-integration coverage lint format local-up local-down deploy shutdown status clean

# Default target
help:
	@echo "ETL Pipeline - Available Commands"
	@echo "=================================="
	@echo ""
	@echo "Setup & Install:"
	@echo "  make setup          - Initial project setup"
	@echo "  make install        - Install Python dependencies"
	@echo ""
	@echo "Local Development:"
	@echo "  make local-up       - Start LocalStack and local services"
	@echo "  make local-down     - Stop local services"
	@echo "  make local-reset    - Reset local environment"
	@echo "  make run-local      - Run ETL pipeline locally"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests"
	@echo "  make test-unit      - Run unit tests only"
	@echo "  make test-integration - Run integration tests"
	@echo "  make coverage       - Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linters"
	@echo "  make format         - Format code"
	@echo ""
	@echo "AWS Deployment:"
	@echo "  make deploy         - Deploy to AWS"
	@echo "  make shutdown       - SHUTDOWN all AWS resources"
	@echo "  make status         - Check AWS resource status"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          - Clean build artifacts"

# Setup
setup: install local-setup
	@echo "Setup complete!"

install:
	pip install -r requirements.txt

local-setup:
	mkdir -p local/localstack-data local/minio-data local/dynamodb-data
	chmod +x local/init-aws.sh 2>/dev/null || true
	chmod +x scripts/*.sh 2>/dev/null || true

# Local Development
local-up:
	docker-compose up -d localstack dynamodb-local
	@echo "Waiting for LocalStack to be ready..."
	@sleep 10
	@echo "Local services are running!"
	@echo "LocalStack: http://localhost:4566"
	@echo "DynamoDB:   http://localhost:8000"

local-down:
	docker-compose down

local-reset:
	docker-compose down -v
	rm -rf local/localstack-data/* local/minio-data/* local/dynamodb-data/*
	docker-compose up -d

run-local:
	ENVIRONMENT=local python scripts/run_local.py

# Testing
test:
	python -m pytest tests/ -v --tb=short

test-unit:
	python -m pytest tests/unit/ -v --tb=short

test-integration:
	python -m pytest tests/integration/ -v --tb=short

coverage:
	python -m pytest tests/ --cov=etl --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in htmlcov/"

# Code Quality
lint:
	flake8 etl/ tests/ scripts/
	mypy etl/ --ignore-missing-imports

format:
	black etl/ tests/ scripts/
	isort etl/ tests/ scripts/

# AWS Deployment
deploy:
	@echo "Deploying to AWS..."
	cd infrastructure/terraform && terraform init && terraform apply -auto-approve
	@echo "Deployment complete!"

plan:
	cd infrastructure/terraform && terraform init && terraform plan

shutdown:
	@echo "============================================"
	@echo "  SHUTTING DOWN ALL AWS RESOURCES"
	@echo "============================================"
	@echo ""
	@read -p "Are you sure? This will destroy all resources! (yes/no): " confirm && \
	if [ "$$confirm" = "yes" ]; then \
		cd infrastructure/terraform && terraform destroy -auto-approve; \
		echo "All resources have been shut down!"; \
	else \
		echo "Shutdown cancelled."; \
	fi

shutdown-force:
	@echo "Force shutting down all resources..."
	cd infrastructure/terraform && terraform destroy -auto-approve
	python scripts/cleanup.py --force --all

status:
	@echo "Checking AWS resource status..."
	python scripts/status_check.py

# Build Lambda package
package:
	@echo "Packaging Lambda function..."
	mkdir -p build/lambda_package
	pip install -r etl/requirements-lambda.txt -t build/lambda_package/
	cp -r etl/src/* build/lambda_package/
	cp etl/lambda_handler.py build/lambda_package/
	cd build/lambda_package && zip -r ../lambda_function.zip .
	@echo "Lambda package created: build/lambda_function.zip"

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
