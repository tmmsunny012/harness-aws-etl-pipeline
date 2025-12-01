#!/usr/bin/env python3
"""
Local ETL Runner
================
Run the ETL pipeline locally against LocalStack or MinIO.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import boto3
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Use force_terminal=True and legacy_windows=False for better Windows compatibility
console = Console(force_terminal=True, legacy_windows=False)

# ASCII-compatible status symbols for Windows
OK = "[green]OK[/green]"
SKIP = "[yellow]--[/yellow]"
FAIL = "[red]XX[/red]"


def setup_local_environment():
    """Configure environment for local testing."""
    os.environ.setdefault("ENVIRONMENT", "local")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")


def check_localstack_health():
    """Check if LocalStack is running and healthy."""
    import requests
    try:
        response = requests.get("http://localhost:4566/_localstack/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def initialize_local_resources():
    """Initialize AWS resources in LocalStack."""
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")

    s3 = boto3.client("s3", endpoint_url=endpoint_url)
    dynamodb = boto3.client("dynamodb", endpoint_url=endpoint_url)
    sns = boto3.client("sns", endpoint_url=endpoint_url)

    # Create S3 buckets
    buckets = [
        "etl-raw-data-local",
        "etl-processed-data-local",
        "etl-archive-local"
    ]

    for bucket in buckets:
        try:
            s3.create_bucket(Bucket=bucket)
            console.print(f"  {OK} Created bucket: {bucket}")
        except s3.exceptions.BucketAlreadyOwnedByYou:
            console.print(f"  {SKIP} Bucket exists: {bucket}")
        except Exception as e:
            console.print(f"  {FAIL} Failed to create {bucket}: {e}")

    # Create DynamoDB table
    try:
        dynamodb.create_table(
            TableName="etl-metadata-local",
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"}
            ],
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"}
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        )
        console.print(f"  {OK} Created DynamoDB table: etl-metadata-local")
    except dynamodb.exceptions.ResourceInUseException:
        console.print(f"  {SKIP} DynamoDB table exists: etl-metadata-local")
    except Exception as e:
        console.print(f"  {FAIL} Failed to create DynamoDB table: {e}")

    # Create SNS topic
    try:
        sns.create_topic(Name="etl-notifications-local")
        console.print(f"  {OK} Created SNS topic: etl-notifications-local")
    except Exception as e:
        console.print(f"  {SKIP} SNS topic: {e}")


def upload_sample_data():
    """Upload sample data to local S3."""
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    s3 = boto3.client("s3", endpoint_url=endpoint_url)

    sample_file = project_root / "sample_data" / "sample_sales.csv"

    if sample_file.exists():
        s3.upload_file(
            str(sample_file),
            "etl-raw-data-local",
            "sample/sample_sales.csv"
        )
        console.print(f"  {OK} Uploaded sample data")
    else:
        console.print(f"  {SKIP} Sample data file not found")


def run_etl_pipeline(event: dict):
    """Run the ETL pipeline with given event."""
    from etl.lambda_handler import handler

    console.print("\n[bold blue]Running ETL Pipeline...[/bold blue]\n")

    start_time = time.time()
    result = handler(event, None)
    duration = time.time() - start_time

    return result, duration


def display_results(result: dict, duration: float):
    """Display ETL results in a nice format."""
    body = result.get("body", {})
    status_code = result.get("statusCode", 500)

    if status_code == 200:
        console.print(Panel(
            f"[bold green]ETL Job Completed Successfully[/bold green]\n\n"
            f"Job ID: {body.get('job_id', 'N/A')}\n"
            f"Duration: {duration:.2f}s",
            title="Success"
        ))

        # Show statistics
        table = Table(title="ETL Statistics")
        table.add_column("Phase", style="cyan")
        table.add_column("Metric", style="magenta")
        table.add_column("Value", style="green")

        # Extract stats
        extract = body.get("extract", {})
        table.add_row("Extract", "Rows Extracted", str(extract.get("rows_extracted", 0)))

        # Transform stats
        transform = body.get("transform", {})
        table.add_row("Transform", "Input Rows", str(transform.get("input_rows", 0)))
        table.add_row("Transform", "Output Rows", str(transform.get("output_rows", 0)))
        table.add_row("Transform", "Rows Removed", str(transform.get("rows_removed", 0)))

        # Load stats
        load = body.get("load", {})
        table.add_row("Load", "Rows Loaded", str(load.get("rows_loaded", 0)))
        table.add_row("Load", "Destination", load.get("destination", "N/A"))

        console.print(table)

    else:
        console.print(Panel(
            f"[bold red]ETL Job Failed[/bold red]\n\n"
            f"Error: {body.get('error', 'Unknown error')}",
            title="Failed"
        ))


def main():
    parser = argparse.ArgumentParser(description="Run ETL pipeline locally")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize local AWS resources"
    )
    parser.add_argument(
        "--upload-sample",
        action="store_true",
        help="Upload sample data to local S3"
    )
    parser.add_argument(
        "--bucket",
        default="etl-raw-data-local",
        help="Source S3 bucket"
    )
    parser.add_argument(
        "--key",
        default="sample/sample_sales.csv",
        help="Source S3 key"
    )
    parser.add_argument(
        "--full-test",
        action="store_true",
        help="Run full test (init + upload + run)"
    )

    args = parser.parse_args()

    console.print(Panel(
        "[bold]ETL Pipeline - Local Runner[/bold]",
        subtitle="Testing against LocalStack"
    ))

    # Setup environment
    setup_local_environment()

    # Check LocalStack
    console.print("\n[bold]Checking LocalStack...[/bold]")
    if not check_localstack_health():
        console.print("[red]LocalStack is not running![/red]")
        console.print("Start it with: docker-compose up -d localstack")
        sys.exit(1)
    console.print("[green]LocalStack is healthy[/green]")

    # Initialize if requested
    if args.init or args.full_test:
        console.print("\n[bold]Initializing local resources...[/bold]")
        initialize_local_resources()

    # Upload sample data if requested
    if args.upload_sample or args.full_test:
        console.print("\n[bold]Uploading sample data...[/bold]")
        upload_sample_data()

    # Run ETL pipeline
    event = {
        "source_bucket": args.bucket,
        "source_key": args.key
    }

    result, duration = run_etl_pipeline(event)
    display_results(result, duration)


if __name__ == "__main__":
    main()
