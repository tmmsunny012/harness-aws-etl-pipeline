"""
Metadata Manager Module
=======================
Handles ETL job metadata storage in DynamoDB.
"""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MetadataManager:
    """
    Manages ETL job metadata in DynamoDB.

    Tracks:
    - Job status (running, success, failed)
    - Job statistics
    - Error information
    - Processing history
    """

    def __init__(self, aws_clients, config):
        """
        Initialize metadata manager.

        Args:
            aws_clients: AWS clients wrapper
            config: Configuration object
        """
        self.aws = aws_clients
        self.config = config
        self.environment = os.environ.get("ENVIRONMENT", "dev")

        # Get table name from environment variable (set by Terraform)
        self.table_name = os.environ.get("DYNAMODB_TABLE")
        if not self.table_name:
            # Fallback for local development
            table_name = config.get("dynamodb.table_name", "etl-metadata")
            self.table_name = f"{table_name}-{self.environment}"

    def _get_table(self):
        """Get DynamoDB table resource."""
        return self.aws.dynamodb_resource.Table(self.table_name)

    def start_job(self, job_id: str, event: Dict[str, Any]) -> bool:
        """
        Record job start in metadata table.

        Args:
            job_id: Unique job identifier
            event: Trigger event data

        Returns:
            True if successful
        """
        try:
            table = self._get_table()
            timestamp = datetime.utcnow().isoformat()

            item = {
                "job_id": job_id,
                "timestamp": timestamp,
                "status": "RUNNING",
                "started_at": timestamp,
                "environment": self.environment,
                "trigger_event": _convert_to_dynamodb_types(event)
            }

            table.put_item(Item=item)
            logger.info(f"Recorded job start: {job_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to record job start: {e}")
            return False

    def complete_job(self, job_id: str, result: Dict[str, Any]) -> bool:
        """
        Record job completion in metadata table.

        Args:
            job_id: Unique job identifier
            result: Job result data

        Returns:
            True if successful
        """
        try:
            table = self._get_table()
            timestamp = datetime.utcnow().isoformat()

            table.update_item(
                Key={
                    "job_id": job_id,
                    "timestamp": self._get_job_timestamp(job_id)
                },
                UpdateExpression="""
                    SET #status = :status,
                        completed_at = :completed_at,
                        job_result = :result,
                        duration_seconds = :duration
                """,
                ExpressionAttributeNames={
                    "#status": "status"
                },
                ExpressionAttributeValues={
                    ":status": "SUCCESS",
                    ":completed_at": timestamp,
                    ":result": _convert_to_dynamodb_types(result),
                    ":duration": Decimal(str(result.get("duration_seconds", 0)))
                }
            )

            logger.info(f"Recorded job completion: {job_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to record job completion: {e}")
            return False

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_traceback: str
    ) -> bool:
        """
        Record job failure in metadata table.

        Args:
            job_id: Unique job identifier
            error_message: Error message
            error_traceback: Full traceback

        Returns:
            True if successful
        """
        try:
            table = self._get_table()
            timestamp = datetime.utcnow().isoformat()

            table.update_item(
                Key={
                    "job_id": job_id,
                    "timestamp": self._get_job_timestamp(job_id)
                },
                UpdateExpression="""
                    SET #status = :status,
                        failed_at = :failed_at,
                        error_message = :error_message,
                        error_traceback = :error_traceback
                """,
                ExpressionAttributeNames={
                    "#status": "status"
                },
                ExpressionAttributeValues={
                    ":status": "FAILED",
                    ":failed_at": timestamp,
                    ":error_message": error_message,
                    ":error_traceback": error_traceback[:10000]  # Truncate if needed
                }
            )

            logger.info(f"Recorded job failure: {job_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to record job failure: {e}")
            return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job metadata by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job metadata or None
        """
        try:
            table = self._get_table()

            response = table.query(
                KeyConditionExpression="job_id = :job_id",
                ExpressionAttributeValues={":job_id": job_id},
                Limit=1
            )

            items = response.get("Items", [])
            return items[0] if items else None

        except Exception as e:
            logger.error(f"Failed to get job: {e}")
            return None

    def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        List recent jobs.

        Args:
            status: Filter by status
            limit: Maximum number of jobs to return

        Returns:
            List of job metadata
        """
        try:
            table = self._get_table()

            if status:
                response = table.scan(
                    FilterExpression="#status = :status",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={":status": status},
                    Limit=limit
                )
            else:
                response = table.scan(Limit=limit)

            return response.get("Items", [])

        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            return []

    def _get_job_timestamp(self, job_id: str) -> str:
        """Get timestamp for a job ID."""
        job = self.get_job(job_id)
        if job:
            return job["timestamp"]
        return datetime.utcnow().isoformat()


def _convert_to_dynamodb_types(obj: Any) -> Any:
    """
    Convert Python types to DynamoDB-compatible types.

    - float -> Decimal
    - nested dicts and lists are processed recursively
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_to_dynamodb_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_dynamodb_types(i) for i in obj]
    elif isinstance(obj, (int, str, bool, type(None))):
        return obj
    else:
        return str(obj)
