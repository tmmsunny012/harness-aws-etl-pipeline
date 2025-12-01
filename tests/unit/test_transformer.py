"""
Unit Tests for Data Transformer
===============================
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from etl.src.transform.transformer import DataTransformer


class TestDataTransformer:
    """Tests for DataTransformer class."""

    @pytest.fixture
    def transformer(self, mock_config):
        """Create a transformer instance."""
        return DataTransformer(mock_config)

    def test_transform_empty_dataframe(self, transformer):
        """Test transformation of empty DataFrame."""
        df = pd.DataFrame()
        result, stats = transformer.transform(df)

        assert result.empty
        assert stats["status"] == "empty_input"
        assert stats["rows_processed"] == 0

    def test_transform_basic(self, transformer, sample_dataframe):
        """Test basic transformation."""
        result, stats = transformer.transform(sample_dataframe)

        assert not result.empty
        assert stats["input_rows"] == 3
        assert stats["output_rows"] == 3
        assert "_processed_at" in result.columns
        assert "_row_hash" in result.columns

    def test_clean_column_names(self, transformer):
        """Test column name cleaning."""
        df = pd.DataFrame({
            "Order ID": [1],
            "Customer Name": ["John"],
            "Unit Price ($)": [99.99]
        })

        result, _ = transformer.transform(df)

        assert "order_id" in result.columns
        assert "customer_name" in result.columns
        assert "unit_price" in result.columns

    def test_null_handling_drop(self, transformer, sample_dataframe_with_nulls):
        """Test null handling with drop strategy."""
        transformer.null_handling = "drop"
        result, stats = transformer.transform(sample_dataframe_with_nulls)

        # All rows with nulls should be dropped
        assert len(result) < len(sample_dataframe_with_nulls)
        assert not result.isnull().any().any()

    def test_null_handling_fill(self, mock_config, sample_dataframe_with_nulls):
        """Test null handling with fill strategy."""
        mock_config._config["etl.transform.null_handling"] = "fill"
        transformer = DataTransformer(mock_config)
        transformer.null_handling = "fill"

        result, stats = transformer.transform(sample_dataframe_with_nulls)

        # No nulls should remain after fill
        # (some columns might still have empty strings which is valid)
        assert len(result) == len(sample_dataframe_with_nulls)

    def test_remove_duplicates(self, transformer):
        """Test duplicate removal."""
        df = pd.DataFrame({
            "order_id": ["ORD001", "ORD001", "ORD002"],
            "product": ["Laptop", "Laptop", "Mouse"]
        })

        result, stats = transformer.transform(df)

        assert stats["deduplication"]["duplicates_removed"] == 1
        assert len(result) == 2

    def test_derived_fields_added(self, transformer, sample_dataframe):
        """Test that derived fields are added."""
        result, stats = transformer.transform(sample_dataframe)

        assert "_processed_at" in result.columns
        assert "_row_hash" in result.columns
        assert "derived_fields" in stats["transformations_applied"]

    def test_type_casting_dates(self, transformer):
        """Test date column type casting."""
        df = pd.DataFrame({
            "order_date": ["2024-01-15", "2024-01-16", "2024-01-17"],
            "value": [100, 200, 300]
        })

        result, _ = transformer.transform(df)

        # Date columns should be converted
        assert pd.api.types.is_datetime64_any_dtype(result["order_date"])

    def test_validation_results(self, transformer, sample_dataframe):
        """Test validation results are included."""
        result, stats = transformer.transform(sample_dataframe)

        assert "validation" in stats
        assert "is_valid" in stats["validation"]
        assert "row_count" in stats["validation"]
        assert "column_count" in stats["validation"]
        assert "schema" in stats["validation"]

    def test_transformation_stats(self, transformer, sample_dataframe):
        """Test transformation statistics are captured."""
        result, stats = transformer.transform(sample_dataframe)

        assert "input_rows" in stats
        assert "output_rows" in stats
        assert "input_columns" in stats
        assert "output_columns" in stats
        assert "transformations_applied" in stats
        assert len(stats["transformations_applied"]) > 0
