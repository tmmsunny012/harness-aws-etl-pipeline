#!/usr/bin/env python3
"""
AWS Resource Cleanup Script
===========================
Safely shuts down and cleans up all AWS resources created by the ETL pipeline.

Usage:
    python scripts/cleanup.py --environment dev
    python scripts/cleanup.py --environment dev --force
    python scripts/cleanup.py --all --force
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

console = Console()


class AWSCleaner:
    """Handles cleanup of AWS resources."""

    def __init__(self, environment: str, region: str = "us-east-1"):
        self.environment = environment
        self.region = region
        self.prefix = f"etl-pipeline-{environment}"

        # Initialize AWS clients
        self.s3 = boto3.client("s3", region_name=region)
        self.dynamodb = boto3.client("dynamodb", region_name=region)
        self.lambda_client = boto3.client("lambda", region_name=region)
        self.sns = boto3.client("sns", region_name=region)
        self.events = boto3.client("events", region_name=region)
        self.logs = boto3.client("logs", region_name=region)
        self.iam = boto3.client("iam", region_name=region)
        self.cloudwatch = boto3.client("cloudwatch", region_name=region)

        self.resources_found = []
        self.resources_deleted = []
        self.errors = []

    def discover_resources(self) -> dict:
        """Discover all resources associated with this deployment."""
        console.print(f"\n[bold]Discovering resources for: {self.prefix}[/bold]\n")

        resources = {
            "s3_buckets": [],
            "lambda_functions": [],
            "dynamodb_tables": [],
            "sns_topics": [],
            "eventbridge_rules": [],
            "log_groups": [],
            "iam_roles": [],
            "cloudwatch_alarms": []
        }

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            # S3 Buckets
            task = progress.add_task("Scanning S3 buckets...", total=None)
            try:
                response = self.s3.list_buckets()
                for bucket in response.get("Buckets", []):
                    if self.prefix in bucket["Name"]:
                        resources["s3_buckets"].append(bucket["Name"])
            except ClientError as e:
                self.errors.append(f"S3: {e}")
            progress.update(task, completed=True)

            # Lambda Functions
            task = progress.add_task("Scanning Lambda functions...", total=None)
            try:
                response = self.lambda_client.list_functions()
                for func in response.get("Functions", []):
                    if self.prefix in func["FunctionName"]:
                        resources["lambda_functions"].append(func["FunctionName"])
            except ClientError as e:
                self.errors.append(f"Lambda: {e}")
            progress.update(task, completed=True)

            # DynamoDB Tables
            task = progress.add_task("Scanning DynamoDB tables...", total=None)
            try:
                response = self.dynamodb.list_tables()
                for table in response.get("TableNames", []):
                    if self.prefix in table:
                        resources["dynamodb_tables"].append(table)
            except ClientError as e:
                self.errors.append(f"DynamoDB: {e}")
            progress.update(task, completed=True)

            # SNS Topics
            task = progress.add_task("Scanning SNS topics...", total=None)
            try:
                response = self.sns.list_topics()
                for topic in response.get("Topics", []):
                    if self.prefix in topic["TopicArn"]:
                        resources["sns_topics"].append(topic["TopicArn"])
            except ClientError as e:
                self.errors.append(f"SNS: {e}")
            progress.update(task, completed=True)

            # EventBridge Rules
            task = progress.add_task("Scanning EventBridge rules...", total=None)
            try:
                response = self.events.list_rules()
                for rule in response.get("Rules", []):
                    if self.prefix in rule["Name"]:
                        resources["eventbridge_rules"].append(rule["Name"])
            except ClientError as e:
                self.errors.append(f"EventBridge: {e}")
            progress.update(task, completed=True)

            # CloudWatch Log Groups
            task = progress.add_task("Scanning CloudWatch log groups...", total=None)
            try:
                paginator = self.logs.get_paginator("describe_log_groups")
                for page in paginator.paginate():
                    for group in page.get("logGroups", []):
                        if self.prefix in group["logGroupName"]:
                            resources["log_groups"].append(group["logGroupName"])
            except ClientError as e:
                self.errors.append(f"CloudWatch Logs: {e}")
            progress.update(task, completed=True)

            # IAM Roles
            task = progress.add_task("Scanning IAM roles...", total=None)
            try:
                paginator = self.iam.get_paginator("list_roles")
                for page in paginator.paginate():
                    for role in page.get("Roles", []):
                        if self.prefix in role["RoleName"]:
                            resources["iam_roles"].append(role["RoleName"])
            except ClientError as e:
                self.errors.append(f"IAM: {e}")
            progress.update(task, completed=True)

            # CloudWatch Alarms
            task = progress.add_task("Scanning CloudWatch alarms...", total=None)
            try:
                response = self.cloudwatch.describe_alarms()
                for alarm in response.get("MetricAlarms", []):
                    if self.prefix in alarm["AlarmName"]:
                        resources["cloudwatch_alarms"].append(alarm["AlarmName"])
            except ClientError as e:
                self.errors.append(f"CloudWatch Alarms: {e}")
            progress.update(task, completed=True)

        return resources

    def display_resources(self, resources: dict):
        """Display discovered resources in a table."""
        table = Table(title=f"Resources Found for {self.prefix}")
        table.add_column("Resource Type", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_column("Names/ARNs", style="green")

        total = 0
        for resource_type, items in resources.items():
            if items:
                total += len(items)
                display_name = resource_type.replace("_", " ").title()
                names = "\n".join(items[:3])
                if len(items) > 3:
                    names += f"\n... and {len(items) - 3} more"
                table.add_row(display_name, str(len(items)), names)

        console.print(table)
        console.print(f"\n[bold]Total resources found: {total}[/bold]")

        return total

    def delete_resources(self, resources: dict, force: bool = False):
        """Delete all discovered resources."""
        console.print("\n[bold red]Starting resource deletion...[/bold red]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            # Delete in reverse dependency order

            # 1. CloudWatch Alarms
            for alarm in resources.get("cloudwatch_alarms", []):
                task = progress.add_task(f"Deleting alarm: {alarm}", total=None)
                try:
                    self.cloudwatch.delete_alarms(AlarmNames=[alarm])
                    self.resources_deleted.append(f"CloudWatch Alarm: {alarm}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete alarm {alarm}: {e}")
                progress.update(task, completed=True)

            # 2. EventBridge Rules
            for rule in resources.get("eventbridge_rules", []):
                task = progress.add_task(f"Deleting EventBridge rule: {rule}", total=None)
                try:
                    # Remove targets first
                    targets = self.events.list_targets_by_rule(Rule=rule)
                    if targets.get("Targets"):
                        target_ids = [t["Id"] for t in targets["Targets"]]
                        self.events.remove_targets(Rule=rule, Ids=target_ids)
                    self.events.delete_rule(Name=rule)
                    self.resources_deleted.append(f"EventBridge Rule: {rule}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete rule {rule}: {e}")
                progress.update(task, completed=True)

            # 3. Lambda Functions
            for func in resources.get("lambda_functions", []):
                task = progress.add_task(f"Deleting Lambda: {func}", total=None)
                try:
                    self.lambda_client.delete_function(FunctionName=func)
                    self.resources_deleted.append(f"Lambda Function: {func}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete Lambda {func}: {e}")
                progress.update(task, completed=True)

            # 4. S3 Buckets (need to empty first)
            for bucket in resources.get("s3_buckets", []):
                task = progress.add_task(f"Deleting S3 bucket: {bucket}", total=None)
                try:
                    # Empty bucket first
                    self._empty_bucket(bucket)
                    self.s3.delete_bucket(Bucket=bucket)
                    self.resources_deleted.append(f"S3 Bucket: {bucket}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete bucket {bucket}: {e}")
                progress.update(task, completed=True)

            # 5. DynamoDB Tables
            for table in resources.get("dynamodb_tables", []):
                task = progress.add_task(f"Deleting DynamoDB table: {table}", total=None)
                try:
                    self.dynamodb.delete_table(TableName=table)
                    self.resources_deleted.append(f"DynamoDB Table: {table}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete table {table}: {e}")
                progress.update(task, completed=True)

            # 6. SNS Topics
            for topic in resources.get("sns_topics", []):
                task = progress.add_task(f"Deleting SNS topic: {topic}", total=None)
                try:
                    self.sns.delete_topic(TopicArn=topic)
                    self.resources_deleted.append(f"SNS Topic: {topic}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete topic {topic}: {e}")
                progress.update(task, completed=True)

            # 7. CloudWatch Log Groups
            for log_group in resources.get("log_groups", []):
                task = progress.add_task(f"Deleting log group: {log_group}", total=None)
                try:
                    self.logs.delete_log_group(logGroupName=log_group)
                    self.resources_deleted.append(f"Log Group: {log_group}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete log group {log_group}: {e}")
                progress.update(task, completed=True)

            # 8. IAM Roles (need to detach policies first)
            for role in resources.get("iam_roles", []):
                task = progress.add_task(f"Deleting IAM role: {role}", total=None)
                try:
                    # Detach policies
                    attached = self.iam.list_attached_role_policies(RoleName=role)
                    for policy in attached.get("AttachedPolicies", []):
                        self.iam.detach_role_policy(
                            RoleName=role,
                            PolicyArn=policy["PolicyArn"]
                        )
                    # Delete inline policies
                    inline = self.iam.list_role_policies(RoleName=role)
                    for policy_name in inline.get("PolicyNames", []):
                        self.iam.delete_role_policy(RoleName=role, PolicyName=policy_name)
                    # Delete role
                    self.iam.delete_role(RoleName=role)
                    self.resources_deleted.append(f"IAM Role: {role}")
                except ClientError as e:
                    self.errors.append(f"Failed to delete role {role}: {e}")
                progress.update(task, completed=True)

    def _empty_bucket(self, bucket: str):
        """Empty an S3 bucket before deletion."""
        try:
            # Delete all objects
            paginator = self.s3.get_paginator("list_object_versions")
            for page in paginator.paginate(Bucket=bucket):
                # Delete versions
                versions = page.get("Versions", [])
                if versions:
                    delete_keys = [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in versions]
                    self.s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})

                # Delete markers
                markers = page.get("DeleteMarkers", [])
                if markers:
                    delete_keys = [{"Key": m["Key"], "VersionId": m["VersionId"]} for m in markers]
                    self.s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
        except ClientError:
            # Try simple delete for non-versioned bucket
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                contents = page.get("Contents", [])
                if contents:
                    delete_keys = [{"Key": obj["Key"]} for obj in contents]
                    self.s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})

    def print_summary(self):
        """Print cleanup summary."""
        console.print("\n")
        console.print(Panel(
            f"[bold green]Cleanup Complete[/bold green]\n\n"
            f"Resources deleted: {len(self.resources_deleted)}\n"
            f"Errors: {len(self.errors)}",
            title="Summary"
        ))

        if self.errors:
            console.print("\n[bold red]Errors encountered:[/bold red]")
            for error in self.errors:
                console.print(f"  - {error}")


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup AWS resources for ETL Pipeline"
    )
    parser.add_argument(
        "--environment", "-e",
        default="dev",
        help="Environment to clean up (dev, staging, prod)"
    )
    parser.add_argument(
        "--region", "-r",
        default="us-east-1",
        help="AWS region"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clean up all environments"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting"
    )

    args = parser.parse_args()

    console.print(Panel(
        "[bold red]AWS Resource Cleanup Tool[/bold red]\n"
        "This will permanently delete AWS resources!",
        title="WARNING"
    ))

    environments = ["dev", "staging", "prod"] if args.all else [args.environment]

    for env in environments:
        console.print(f"\n[bold]Processing environment: {env}[/bold]")

        cleaner = AWSCleaner(env, args.region)
        resources = cleaner.discover_resources()
        total = cleaner.display_resources(resources)

        if total == 0:
            console.print(f"[yellow]No resources found for {env}[/yellow]")
            continue

        if args.dry_run:
            console.print("[yellow]DRY RUN - No resources were deleted[/yellow]")
            continue

        if not args.force:
            if not Confirm.ask(f"\nDelete all {total} resources for {env}?"):
                console.print("[yellow]Skipped[/yellow]")
                continue

        cleaner.delete_resources(resources, force=args.force)
        cleaner.print_summary()

    console.print("\n[bold green]Cleanup process completed![/bold green]")


if __name__ == "__main__":
    main()
