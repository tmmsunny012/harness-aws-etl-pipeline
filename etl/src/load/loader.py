"""
Data Loader Module
==================
Handles loading transformed data to target destinations.
"""

import io
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DataLoader:
    """
    Loads data to target destinations.

    Supports:
    - S3 (Parquet, CSV, JSON)
    - Partitioned storage
    - Metadata tracking
    """

    def __init__(self, aws_clients, config):
        """
        Initialize the loader.

        Args:
            aws_clients: AWS clients wrapper
            config: Configuration object
        """
        self.aws = aws_clients
        self.config = config
        self.s3 = aws_clients.s3
        self.output_format = config.get("etl.load.output_format", "parquet")
        self.compression = config.get("etl.load.compression", "snappy")

    def load(self, df: pd.DataFrame, job_id: str) -> Dict[str, Any]:
        """
        Load data to the target destination.

        Args:
            df: Transformed DataFrame
            job_id: Unique job identifier

        Returns:
            Load result dictionary
        """
        if df.empty:
            logger.warning("Empty DataFrame, nothing to load")
            return {
                "status": "skipped",
                "reason": "empty_dataframe",
                "rows_loaded": 0
            }

        # Get target bucket from environment variable (set by Terraform)
        bucket = os.environ.get("S3_PROCESSED_BUCKET")
        if not bucket:
            # Fallback for local development
            env = os.environ.get("ENVIRONMENT", "dev")
            bucket = self.config.get("s3.processed_bucket_prefix", "etl-processed-data")
            bucket = f"{bucket}-{env}"

        # Generate output path with partitioning
        output_path = self._generate_output_path(df, job_id)

        # Write to S3
        result = self._write_to_s3(df, bucket, output_path)

        return result

    def _generate_output_path(self, df: pd.DataFrame, job_id: str) -> str:
        """
        Generate partitioned output path.

        Args:
            df: DataFrame to determine partitions
            job_id: Job identifier

        Returns:
            S3 key path
        """
        now = datetime.utcnow()

        # Create partition path
        partition_path = f"year={now.year}/month={now.month:02d}/day={now.day:02d}"

        # Add job-specific path
        filename = f"{job_id}.{self.output_format}"

        return f"processed/{partition_path}/{filename}"

    def _write_to_s3(
        self,
        df: pd.DataFrame,
        bucket: str,
        key: str
    ) -> Dict[str, Any]:
        """
        Write DataFrame to S3.

        Args:
            df: DataFrame to write
            bucket: Target S3 bucket
            key: S3 object key

        Returns:
            Write result dictionary
        """
        logger.info(f"Writing {len(df)} rows to s3://{bucket}/{key}")

        # Serialize based on format
        buffer = io.BytesIO()

        if self.output_format == "parquet":
            df.to_parquet(buffer, compression=self.compression, index=False)
        elif self.output_format == "csv":
            df.to_csv(buffer, index=False)
        elif self.output_format == "json":
            df.to_json(buffer, orient="records", lines=True)
        else:
            raise ValueError(f"Unsupported output format: {self.output_format}")

        # Get buffer size
        buffer.seek(0, 2)  # Seek to end
        file_size = buffer.tell()
        buffer.seek(0)  # Seek back to start

        # Upload to S3
        self.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue(),
            ContentType=self._get_content_type()
        )

        logger.info(f"Successfully wrote {file_size} bytes to s3://{bucket}/{key}")

        return {
            "status": "success",
            "destination": f"s3://{bucket}/{key}",
            "format": self.output_format,
            "compression": self.compression if self.output_format == "parquet" else None,
            "rows_loaded": len(df),
            "file_size_bytes": file_size
        }

    def _get_content_type(self) -> str:
        """Get content type for output format."""
        content_types = {
            "parquet": "application/octet-stream",
            "csv": "text/csv",
            "json": "application/json"
        }
        return content_types.get(self.output_format, "application/octet-stream")

    def archive_source(self, source_bucket: str, source_key: str) -> Dict[str, Any]:
        """
        Archive the source file after processing.

        Args:
            source_bucket: Source S3 bucket
            source_key: Source S3 key

        Returns:
            Archive result dictionary
        """
        env = os.environ.get("ENVIRONMENT", "dev")
        archive_bucket = f"{self.config.get('s3.archive_bucket_prefix', 'etl-archive')}-{env}"

        # Generate archive path
        now = datetime.utcnow()
        archive_key = f"archive/{now.year}/{now.month:02d}/{source_key}"

        try:
            # Copy to archive
            self.s3.copy_object(
                CopySource={"Bucket": source_bucket, "Key": source_key},
                Bucket=archive_bucket,
                Key=archive_key
            )

            # Delete from source
            self.s3.delete_object(Bucket=source_bucket, Key=source_key)

            logger.info(f"Archived {source_key} to {archive_bucket}/{archive_key}")

            return {
                "status": "archived",
                "source": f"s3://{source_bucket}/{source_key}",
                "archive": f"s3://{archive_bucket}/{archive_key}"
            }

        except Exception as e:
            logger.error(f"Failed to archive {source_key}: {e}")
            return {
                "status": "archive_failed",
                "error": str(e)
            }
