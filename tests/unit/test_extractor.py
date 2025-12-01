"""
Unit Tests for Data Extractor
=============================
"""

import pytest
import pandas as pd
from unittest.mock import Mock, MagicMock
import io
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from etl.src.extract.extractor import DataExtractor


class TestDataExtractor:
    """Tests for DataExtractor class."""

    @pytest.fixture
    def mock_aws_clients(self, sample_csv_content):
        """Create mock AWS clients."""
        mock_clients = Mock()
        mock_s3 = Mock()

        # Mock S3 get_object
        mock_s3.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=sample_csv_content))
        }

        # Mock S3 paginator
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "data/file1.csv"},
                    {"Key": "data/file2.csv"}
                ]
            }
        ]
        mock_s3.get_paginator.return_value = mock_paginator

        mock_clients.s3 = mock_s3
        return mock_clients

    @pytest.fixture
    def extractor(self, mock_aws_clients, mock_config):
        """Create an extractor instance."""
        return DataExtractor(mock_aws_clients, mock_config)

    def test_get_file_format_csv(self):
        """Test CSV format detection."""
        assert DataExtractor._get_file_format("data/file.csv") == "csv"
        assert DataExtractor._get_file_format("data/FILE.CSV") == "csv"

    def test_get_file_format_json(self):
        """Test JSON format detection."""
        assert DataExtractor._get_file_format("data/file.json") == "json"
        assert DataExtractor._get_file_format("data/file.jsonl") == "json"

    def test_get_file_format_parquet(self):
        """Test Parquet format detection."""
        assert DataExtractor._get_file_format("data/file.parquet") == "parquet"

    def test_get_file_format_unknown(self):
        """Test unknown format detection."""
        assert DataExtractor._get_file_format("data/file.txt") == "unknown"
        assert DataExtractor._get_file_format("data/file.xlsx") == "unknown"

    def test_extract_single_csv(self, extractor, sample_csv_content):
        """Test single CSV file extraction."""
        result = extractor._extract_single_file("test-bucket", "data/test.csv")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert "order_id" in result.columns

    def test_extract_unsupported_format(self, extractor):
        """Test extraction of unsupported format raises error."""
        with pytest.raises(ValueError, match="Unsupported file format"):
            extractor._extract_single_file("test-bucket", "data/test.txt")

    def test_extract_s3_source(self, extractor):
        """Test extraction from S3 source info."""
        source_info = {
            "type": "s3",
            "bucket": "test-bucket",
            "key": "data/test.csv"
        }

        result = extractor.extract(source_info)
        assert isinstance(result, pd.DataFrame)

    def test_extract_direct_source(self, extractor):
        """Test extraction from direct source info."""
        source_info = {
            "type": "direct",
            "bucket": "test-bucket",
            "key": "data/test.csv"
        }

        result = extractor.extract(source_info)
        assert isinstance(result, pd.DataFrame)

    def test_list_s3_files(self, extractor):
        """Test S3 file listing."""
        files = extractor._list_s3_files("test-bucket", "data/")

        assert len(files) == 2
        assert "data/file1.csv" in files
        assert "data/file2.csv" in files

    def test_extract_batch_empty(self, extractor):
        """Test batch extraction with no files."""
        # Override mock to return empty
        extractor.s3.get_paginator.return_value.paginate.return_value = [{}]

        source_info = {
            "type": "batch",
            "bucket": "test-bucket",
            "prefix": "empty/"
        }

        result = extractor.extract(source_info)
        assert result.empty

    def test_supported_formats(self, extractor):
        """Test that supported formats are correctly defined."""
        assert "csv" in DataExtractor.SUPPORTED_FORMATS
        assert "json" in DataExtractor.SUPPORTED_FORMATS
        assert "parquet" in DataExtractor.SUPPORTED_FORMATS
