"""
AWS Clients Module
==================
Centralized AWS client management with LocalStack support.
"""

import logging
import os
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)


class AWSClients:
    """
    Manages AWS service clients with support for LocalStack.

    Automatically configures clients for:
    - Local development (LocalStack)
    - AWS cloud environments
    """

    def __init__(self, config):
        """
        Initialize AWS clients.

        Args:
            config: Configuration object
        """
        self.config = config
        self.environment = os.environ.get("ENVIRONMENT", "dev")
        self.endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        self.region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

        # Check if running locally
        self.is_local = (
            self.environment == "local" or
            self.endpoint_url is not None
        )

        if self.is_local:
            logger.info(f"Running in LOCAL mode with endpoint: {self.endpoint_url}")
        else:
            logger.info(f"Running in AWS mode in region: {self.region}")

        # Initialize clients
        self._s3 = None
        self._dynamodb = None
        self._sns = None
        self._events = None
        self._cloudwatch = None
        self._lambda = None

    def _get_client_kwargs(self) -> dict:
        """Get common kwargs for boto3 client creation."""
        kwargs = {
            "region_name": self.region,
            "config": BotoConfig(
                retries={"max_attempts": 3, "mode": "adaptive"}
            )
        }

        if self.is_local and self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
            kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
            kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")

        return kwargs

    @property
    def s3(self):
        """Get S3 client."""
        if self._s3 is None:
            self._s3 = boto3.client("s3", **self._get_client_kwargs())
        return self._s3

    @property
    def dynamodb(self):
        """Get DynamoDB client."""
        if self._dynamodb is None:
            self._dynamodb = boto3.client("dynamodb", **self._get_client_kwargs())
        return self._dynamodb

    @property
    def dynamodb_resource(self):
        """Get DynamoDB resource (for Table operations)."""
        return boto3.resource("dynamodb", **self._get_client_kwargs())

    @property
    def sns(self):
        """Get SNS client."""
        if self._sns is None:
            self._sns = boto3.client("sns", **self._get_client_kwargs())
        return self._sns

    @property
    def events(self):
        """Get EventBridge client."""
        if self._events is None:
            self._events = boto3.client("events", **self._get_client_kwargs())
        return self._events

    @property
    def cloudwatch(self):
        """Get CloudWatch client."""
        if self._cloudwatch is None:
            self._cloudwatch = boto3.client("cloudwatch", **self._get_client_kwargs())
        return self._cloudwatch

    @property
    def lambda_client(self):
        """Get Lambda client."""
        if self._lambda is None:
            self._lambda = boto3.client("lambda", **self._get_client_kwargs())
        return self._lambda

    def send_notification(self, subject: str, message: str) -> Optional[str]:
        """
        Send notification via SNS.

        Args:
            subject: Notification subject
            message: Notification message

        Returns:
            Message ID if successful, None otherwise
        """
        # Get topic ARN from environment variable (set by Terraform)
        topic_arn = os.environ.get("SNS_TOPIC_ARN")
        if not topic_arn:
            # Fallback for local development
            topic_name = self.config.get("sns.topic_name", "etl-notifications")
            env = os.environ.get("ENVIRONMENT", "dev")
            topic_arn = self._get_sns_topic_arn(f"{topic_name}-{env}")

        if not topic_arn:
            logger.warning("SNS topic not found, skipping notification")
            return None

        try:
            response = self.sns.publish(
                TopicArn=topic_arn,
                Subject=subject[:100],  # SNS subject limit
                Message=message
            )
            logger.info(f"Sent notification: {response['MessageId']}")
            return response["MessageId"]
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return None

    def _get_sns_topic_arn(self, topic_name: str) -> Optional[str]:
        """Get SNS topic ARN by name."""
        try:
            response = self.sns.list_topics()
            for topic in response.get("Topics", []):
                if topic["TopicArn"].endswith(f":{topic_name}"):
                    return topic["TopicArn"]
        except Exception as e:
            logger.error(f"Failed to get SNS topic: {e}")
        return None

    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: Optional[dict] = None
    ):
        """
        Put custom metric to CloudWatch.

        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Metric unit
            dimensions: Optional dimensions
        """
        namespace = self.config.get("monitoring.cloudwatch.metric_namespace", "ETL/Pipeline")

        metric_data = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit
        }

        if dimensions:
            metric_data["Dimensions"] = [
                {"Name": k, "Value": v} for k, v in dimensions.items()
            ]

        try:
            self.cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=[metric_data]
            )
        except Exception as e:
            logger.error(f"Failed to put metric: {e}")
