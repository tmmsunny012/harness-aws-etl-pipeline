#!/usr/bin/env python3
"""
AWS Resource Status Check
=========================
Check the status of all deployed AWS resources and estimate costs.

Usage:
    python scripts/status_check.py
    python scripts/status_check.py --environment dev
    python scripts/status_check.py --detailed
"""

import argparse
import os
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class ResourceChecker:
    """Check status of AWS resources."""

    def __init__(self, environment: str, region: str = "us-east-1"):
        self.environment = environment
        self.region = region
        self.prefix = f"etl-pipeline-{environment}"

        # Initialize clients
        self.s3 = boto3.client("s3", region_name=region)
        self.dynamodb = boto3.client("dynamodb", region_name=region)
        self.lambda_client = boto3.client("lambda", region_name=region)
        self.cloudwatch = boto3.client("cloudwatch", region_name=region)
        self.logs = boto3.client("logs", region_name=region)

    def check_all(self) -> dict:
        """Check status of all resources."""
        status = {
            "s3": self._check_s3(),
            "lambda": self._check_lambda(),
            "dynamodb": self._check_dynamodb(),
            "recent_jobs": self._check_recent_jobs()
        }
        return status

    def _check_s3(self) -> dict:
        """Check S3 bucket status."""
        buckets = {}
        try:
            response = self.s3.list_buckets()
            for bucket in response.get("Buckets", []):
                if self.prefix in bucket["Name"]:
                    # Get bucket size
                    try:
                        size = self._get_bucket_size(bucket["Name"])
                        object_count = self._get_object_count(bucket["Name"])
                        buckets[bucket["Name"]] = {
                            "status": "active",
                            "size_mb": round(size / (1024 * 1024), 2),
                            "object_count": object_count,
                            "created": bucket["CreationDate"].isoformat()
                        }
                    except Exception:
                        buckets[bucket["Name"]] = {"status": "active", "size_mb": "N/A"}
        except ClientError as e:
            return {"error": str(e)}
        return buckets

    def _get_bucket_size(self, bucket: str) -> int:
        """Get total size of bucket in bytes."""
        total_size = 0
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                total_size += obj.get("Size", 0)
        return total_size

    def _get_object_count(self, bucket: str) -> int:
        """Get count of objects in bucket."""
        count = 0
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            count += len(page.get("Contents", []))
        return count

    def _check_lambda(self) -> dict:
        """Check Lambda function status."""
        functions = {}
        try:
            response = self.lambda_client.list_functions()
            for func in response.get("Functions", []):
                if self.prefix in func["FunctionName"]:
                    # Get invocation metrics
                    invocations = self._get_lambda_invocations(func["FunctionName"])
                    functions[func["FunctionName"]] = {
                        "status": func["State"] if "State" in func else "Active",
                        "runtime": func["Runtime"],
                        "memory_mb": func["MemorySize"],
                        "timeout": func["Timeout"],
                        "last_modified": func["LastModified"],
                        "invocations_24h": invocations
                    }
        except ClientError as e:
            return {"error": str(e)}
        return functions

    def _get_lambda_invocations(self, function_name: str) -> int:
        """Get Lambda invocation count for last 24 hours."""
        try:
            response = self.cloudwatch.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName="Invocations",
                Dimensions=[{"Name": "FunctionName", "Value": function_name}],
                StartTime=datetime.utcnow() - timedelta(hours=24),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=["Sum"]
            )
            datapoints = response.get("Datapoints", [])
            return int(datapoints[0]["Sum"]) if datapoints else 0
        except Exception:
            return 0

    def _check_dynamodb(self) -> dict:
        """Check DynamoDB table status."""
        tables = {}
        try:
            response = self.dynamodb.list_tables()
            for table_name in response.get("TableNames", []):
                if self.prefix in table_name:
                    desc = self.dynamodb.describe_table(TableName=table_name)
                    table = desc["Table"]
                    tables[table_name] = {
                        "status": table["TableStatus"],
                        "item_count": table.get("ItemCount", 0),
                        "size_bytes": table.get("TableSizeBytes", 0),
                        "read_capacity": table["ProvisionedThroughput"]["ReadCapacityUnits"],
                        "write_capacity": table["ProvisionedThroughput"]["WriteCapacityUnits"]
                    }
        except ClientError as e:
            return {"error": str(e)}
        return tables

    def _check_recent_jobs(self) -> list:
        """Get recent ETL job executions from DynamoDB."""
        jobs = []
        try:
            table_name = f"{self.prefix}-metadata"
            response = self.dynamodb.scan(
                TableName=table_name,
                Limit=10
            )
            for item in response.get("Items", []):
                jobs.append({
                    "job_id": item.get("job_id", {}).get("S", "N/A"),
                    "status": item.get("status", {}).get("S", "N/A"),
                    "timestamp": item.get("timestamp", {}).get("S", "N/A")
                })
        except ClientError:
            pass
        return jobs

    def estimate_costs(self, status: dict) -> dict:
        """Estimate current monthly costs based on usage."""
        costs = {
            "s3_storage": 0.0,
            "dynamodb": 0.0,
            "lambda": 0.0,
            "total_estimated": 0.0,
            "within_free_tier": True
        }

        # S3 cost estimation (first 5GB free)
        total_s3_mb = sum(
            b.get("size_mb", 0) for b in status.get("s3", {}).values()
            if isinstance(b, dict)
        )
        if total_s3_mb > 5120:  # 5GB in MB
            costs["s3_storage"] = (total_s3_mb - 5120) * 0.023 / 1024

        # DynamoDB cost (first 25 RCU/WCU free)
        for table in status.get("dynamodb", {}).values():
            if isinstance(table, dict):
                rcu = table.get("read_capacity", 0)
                wcu = table.get("write_capacity", 0)
                if rcu > 25 or wcu > 25:
                    costs["dynamodb"] += (max(0, rcu - 25) * 0.00013 + max(0, wcu - 25) * 0.00065) * 720

        # Lambda cost (first 1M requests and 400,000 GB-seconds free)
        total_invocations = sum(
            f.get("invocations_24h", 0) for f in status.get("lambda", {}).values()
            if isinstance(f, dict)
        ) * 30  # Estimate monthly

        if total_invocations > 1000000:
            costs["lambda"] = (total_invocations - 1000000) * 0.0000002

        costs["total_estimated"] = costs["s3_storage"] + costs["dynamodb"] + costs["lambda"]
        costs["within_free_tier"] = costs["total_estimated"] < 0.01

        return costs

    def display_status(self, status: dict, detailed: bool = False):
        """Display status in formatted tables."""
        # Header
        console.print(Panel(
            f"[bold]ETL Pipeline Status Report[/bold]\n"
            f"Environment: {self.environment}\n"
            f"Region: {self.region}\n"
            f"Time: {datetime.now().isoformat()}",
            title="Status Report"
        ))

        # S3 Status
        if status.get("s3"):
            table = Table(title="S3 Buckets")
            table.add_column("Bucket", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Size (MB)", style="magenta")
            table.add_column("Objects", style="yellow")

            for name, info in status["s3"].items():
                if isinstance(info, dict) and "error" not in info:
                    table.add_row(
                        name.split("-")[-2],  # Simplified name
                        info.get("status", "N/A"),
                        str(info.get("size_mb", "N/A")),
                        str(info.get("object_count", "N/A"))
                    )
            console.print(table)

        # Lambda Status
        if status.get("lambda"):
            table = Table(title="Lambda Functions")
            table.add_column("Function", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Memory", style="magenta")
            table.add_column("Invocations (24h)", style="yellow")

            for name, info in status["lambda"].items():
                if isinstance(info, dict) and "error" not in info:
                    table.add_row(
                        name.split("-")[-1],
                        info.get("status", "N/A"),
                        f"{info.get('memory_mb', 'N/A')} MB",
                        str(info.get("invocations_24h", 0))
                    )
            console.print(table)

        # DynamoDB Status
        if status.get("dynamodb"):
            table = Table(title="DynamoDB Tables")
            table.add_column("Table", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Items", style="magenta")
            table.add_column("RCU/WCU", style="yellow")

            for name, info in status["dynamodb"].items():
                if isinstance(info, dict) and "error" not in info:
                    table.add_row(
                        name.split("-")[-1],
                        info.get("status", "N/A"),
                        str(info.get("item_count", 0)),
                        f"{info.get('read_capacity', 0)}/{info.get('write_capacity', 0)}"
                    )
            console.print(table)

        # Recent Jobs
        if status.get("recent_jobs") and detailed:
            table = Table(title="Recent ETL Jobs")
            table.add_column("Job ID", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Timestamp", style="yellow")

            for job in status["recent_jobs"][:5]:
                status_style = "green" if job["status"] == "SUCCESS" else "red"
                table.add_row(
                    job["job_id"],
                    f"[{status_style}]{job['status']}[/{status_style}]",
                    job["timestamp"]
                )
            console.print(table)

        # Cost Estimation
        costs = self.estimate_costs(status)
        cost_status = "[green]Within Free Tier[/green]" if costs["within_free_tier"] else f"[yellow]${costs['total_estimated']:.4f}/month[/yellow]"

        console.print(Panel(
            f"[bold]Cost Estimation[/bold]\n\n"
            f"S3 Storage: ${costs['s3_storage']:.4f}\n"
            f"DynamoDB: ${costs['dynamodb']:.4f}\n"
            f"Lambda: ${costs['lambda']:.4f}\n"
            f"─────────────────\n"
            f"Total: {cost_status}",
            title="Monthly Cost Estimate"
        ))


def main():
    parser = argparse.ArgumentParser(description="Check AWS resource status")
    parser.add_argument(
        "--environment", "-e",
        default="dev",
        help="Environment to check"
    )
    parser.add_argument(
        "--region", "-r",
        default="us-east-1",
        help="AWS region"
    )
    parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    checker = ResourceChecker(args.environment, args.region)
    status = checker.check_all()

    if args.json:
        import json
        print(json.dumps(status, indent=2, default=str))
    else:
        checker.display_status(status, detailed=args.detailed)


if __name__ == "__main__":
    main()
