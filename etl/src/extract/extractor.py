"""
Data Extractor Module
=====================
Handles extraction of data from various sources (S3, etc.)
"""

import io
import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class DataExtractor:
    """
    Extracts data from source systems.

    Supports:
    - CSV files from S3
    - JSON files from S3
    - Parquet files from S3
    - Batch extraction of multiple files
    """

    SUPPORTED_FORMATS = ["csv", "json", "parquet"]

    def __init__(self, aws_clients, config):
        """
        Initialize the extractor.

        Args:
            aws_clients: AWS clients wrapper
            config: Configuration object
        """
        self.aws = aws_clients
        self.config = config
        self.s3 = aws_clients.s3

    def extract(self, source_info: Dict[str, Any]) -> pd.DataFrame:
        """
        Extract data based on source information.

        Args:
            source_info: Dictionary containing source details

        Returns:
            Pandas DataFrame with extracted data
        """
        source_type = source_info.get("type", "s3")

        if source_type == "s3" or source_type == "direct":
            return self._extract_single_file(
                source_info["bucket"],
                source_info["key"]
            )
        elif source_type == "batch":
            return self._extract_batch(
                source_info["bucket"],
                source_info.get("prefix", "")
            )
        elif source_type == "scheduled":
            # For scheduled runs, process all pending files
            bucket = self.config.get("s3.raw_bucket_prefix")
            return self._extract_batch(bucket, "pending/")
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

    def _extract_single_file(self, bucket: str, key: str) -> pd.DataFrame:
        """
        Extract data from a single S3 file.

        Args:
            bucket: S3 bucket name
            key: S3 object key

        Returns:
            Pandas DataFrame
        """
        logger.info(f"Extracting file: s3://{bucket}/{key}")

        # Determine file format
        file_format = self._get_file_format(key)
        if file_format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {file_format}")

        # Download file from S3
        response = self.s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read()

        # Parse based on format
        if file_format == "csv":
            df = pd.read_csv(io.BytesIO(content))
        elif file_format == "json":
            df = pd.read_json(io.BytesIO(content), lines=True)
        elif file_format == "parquet":
            df = pd.read_parquet(io.BytesIO(content))

        logger.info(f"Extracted {len(df)} rows from {key}")
        return df

    def _extract_batch(self, bucket: str, prefix: str) -> pd.DataFrame:
        """
        Extract and combine data from multiple S3 files.

        Args:
            bucket: S3 bucket name
            prefix: S3 key prefix to filter files

        Returns:
            Combined Pandas DataFrame
        """
        logger.info(f"Batch extracting from s3://{bucket}/{prefix}")

        # List all objects with prefix
        files = self._list_s3_files(bucket, prefix)

        if not files:
            logger.warning(f"No files found in s3://{bucket}/{prefix}")
            return pd.DataFrame()

        # Extract and combine all files
        dataframes = []
        for file_key in files:
            try:
                df = self._extract_single_file(bucket, file_key)
                dataframes.append(df)
            except Exception as e:
                logger.error(f"Failed to extract {file_key}: {e}")

        if not dataframes:
            return pd.DataFrame()

        # Combine all dataframes
        combined_df = pd.concat(dataframes, ignore_index=True)
        logger.info(f"Combined {len(dataframes)} files into {len(combined_df)} rows")

        return combined_df

    def _list_s3_files(self, bucket: str, prefix: str) -> List[str]:
        """
        List all files in S3 with given prefix.

        Args:
            bucket: S3 bucket name
            prefix: S3 key prefix

        Returns:
            List of S3 keys
        """
        files = []
        paginator = self.s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    if self._get_file_format(key) in self.SUPPORTED_FORMATS:
                        files.append(key)

        return files

    @staticmethod
    def _get_file_format(key: str) -> str:
        """
        Determine file format from S3 key.

        Args:
            key: S3 object key

        Returns:
            File format string
        """
        key_lower = key.lower()
        if key_lower.endswith(".csv"):
            return "csv"
        elif key_lower.endswith(".json") or key_lower.endswith(".jsonl"):
            return "json"
        elif key_lower.endswith(".parquet"):
            return "parquet"
        else:
            return "unknown"
