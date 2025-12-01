"""
Unit Tests for Data Loader
==========================
"""

import pytest
import pandas as pd
from unittest.mock import Mock, MagicMock, patch
import io
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from etl.src.load.loader import DataLoader


class TestDataLoader:
    """Tests for DataLoader class."""

    @pytest.fixture
    def mock_aws_clients(self):
        """Create mock AWS clients."""
        mock_clients = Mock()
        mock_s3 = Mock()
        mock_s3.put_object.return_value = {}
        mock_clients.s3 = mock_s3
        return mock_clients

    @pytest.fixture
    def loader(self, mock_aws_clients, mock_config):
        """Create a loader instance."""
        return DataLoader(mock_aws_clients, mock_config)

    def test_load_empty_dataframe(self, loader):
        """Test loading empty DataFrame returns skip status."""
        df = pd.DataFrame()
        result = loader.load(df, "test-job-001")

        assert result["status"] == "skipped"
        assert result["reason"] == "empty_dataframe"
        assert result["rows_loaded"] == 0

    def test_load_success(self, loader, sample_dataframe):
        """Test successful data loading."""
        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            result = loader.load(sample_dataframe, "test-job-001")

        assert result["status"] == "success"
        assert result["rows_loaded"] == 3
        assert "destination" in result
        assert result["format"] == "parquet"

    def test_generate_output_path(self, loader, sample_dataframe):
        """Test output path generation."""
        path = loader._generate_output_path(sample_dataframe, "test-job-001")

        assert "processed/" in path
        assert "year=" in path
        assert "month=" in path
        assert "day=" in path
        assert "test-job-001" in path
        assert path.endswith(".parquet")

    def test_get_content_type_parquet(self, loader):
        """Test content type for parquet."""
        loader.output_format = "parquet"
        assert loader._get_content_type() == "application/octet-stream"

    def test_get_content_type_csv(self, loader):
        """Test content type for CSV."""
        loader.output_format = "csv"
        assert loader._get_content_type() == "text/csv"

    def test_get_content_type_json(self, loader):
        """Test content type for JSON."""
        loader.output_format = "json"
        assert loader._get_content_type() == "application/json"

    def test_write_to_s3_parquet(self, loader, sample_dataframe):
        """Test writing parquet to S3."""
        result = loader._write_to_s3(
            sample_dataframe,
            "test-bucket",
            "test/output.parquet"
        )

        assert result["status"] == "success"
        assert result["format"] == "parquet"
        assert result["compression"] == "snappy"
        loader.s3.put_object.assert_called_once()

    def test_write_to_s3_csv(self, loader, sample_dataframe):
        """Test writing CSV to S3."""
        loader.output_format = "csv"

        result = loader._write_to_s3(
            sample_dataframe,
            "test-bucket",
            "test/output.csv"
        )

        assert result["status"] == "success"
        assert result["format"] == "csv"

    def test_write_to_s3_json(self, loader, sample_dataframe):
        """Test writing JSON to S3."""
        loader.output_format = "json"

        result = loader._write_to_s3(
            sample_dataframe,
            "test-bucket",
            "test/output.json"
        )

        assert result["status"] == "success"
        assert result["format"] == "json"

    def test_unsupported_format_raises_error(self, loader, sample_dataframe):
        """Test unsupported format raises ValueError."""
        loader.output_format = "xlsx"

        with pytest.raises(ValueError, match="Unsupported output format"):
            loader._write_to_s3(
                sample_dataframe,
                "test-bucket",
                "test/output.xlsx"
            )

    def test_archive_source_success(self, loader):
        """Test successful source archival."""
        loader.s3.copy_object.return_value = {}
        loader.s3.delete_object.return_value = {}

        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            result = loader.archive_source("source-bucket", "data/file.csv")

        assert result["status"] == "archived"
        assert "source" in result
        assert "archive" in result

    def test_archive_source_failure(self, loader):
        """Test source archival failure handling."""
        loader.s3.copy_object.side_effect = Exception("Copy failed")

        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            result = loader.archive_source("source-bucket", "data/file.csv")

        assert result["status"] == "archive_failed"
        assert "error" in result
