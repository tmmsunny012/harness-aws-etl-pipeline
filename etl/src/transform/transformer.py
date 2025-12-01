"""
Data Transformer Module
=======================
Handles data transformation, cleaning, and validation.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataTransformer:
    """
    Transforms and cleans data.

    Features:
    - Null handling (drop, fill, flag)
    - Type casting
    - Data validation
    - Derived field creation
    - Deduplication
    """

    def __init__(self, config):
        """
        Initialize the transformer.

        Args:
            config: Configuration object
        """
        self.config = config
        self.null_handling = config.get("etl.transform.null_handling", "drop")
        self.date_format = config.get("etl.transform.date_format", "%Y-%m-%d")

    def transform(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Apply all transformations to the data.

        Args:
            df: Input DataFrame

        Returns:
            Tuple of (transformed DataFrame, transformation statistics)
        """
        if df.empty:
            return df, {"status": "empty_input", "rows_processed": 0}

        stats = {
            "input_rows": len(df),
            "input_columns": len(df.columns),
            "transformations_applied": []
        }

        logger.info(f"Starting transformation of {len(df)} rows")

        # Step 1: Clean column names
        df = self._clean_column_names(df)
        stats["transformations_applied"].append("clean_column_names")

        # Step 2: Handle nulls
        df, null_stats = self._handle_nulls(df)
        stats["null_handling"] = null_stats
        stats["transformations_applied"].append("null_handling")

        # Step 3: Remove duplicates
        df, dedup_stats = self._remove_duplicates(df)
        stats["deduplication"] = dedup_stats
        stats["transformations_applied"].append("deduplication")

        # Step 4: Type casting
        df = self._cast_types(df)
        stats["transformations_applied"].append("type_casting")

        # Step 5: Add derived fields
        df = self._add_derived_fields(df)
        stats["transformations_applied"].append("derived_fields")

        # Step 6: Validate data
        validation_result = self._validate_data(df)
        stats["validation"] = validation_result

        # Final stats
        stats["output_rows"] = len(df)
        stats["output_columns"] = len(df.columns)
        stats["rows_removed"] = stats["input_rows"] - stats["output_rows"]

        logger.info(f"Transformation complete: {stats['output_rows']} rows output")

        return df, stats

    def _clean_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names.

        - Convert to lowercase
        - Replace spaces with underscores
        - Remove special characters
        - Clean up multiple/trailing underscores
        """
        df.columns = (
            df.columns
            .str.lower()
            .str.replace(" ", "_", regex=False)
            .str.replace(r"[^\w]", "", regex=True)
            .str.replace(r"_+", "_", regex=True)  # Replace multiple underscores with single
            .str.strip("_")  # Remove leading/trailing underscores
        )
        return df

    def _handle_nulls(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Handle null values based on configuration.

        Args:
            df: Input DataFrame

        Returns:
            Tuple of (processed DataFrame, null statistics)
        """
        null_counts_before = df.isnull().sum().to_dict()
        total_nulls = df.isnull().sum().sum()

        if self.null_handling == "drop":
            # Drop rows with any null values
            df = df.dropna()
        elif self.null_handling == "fill":
            # Fill nulls with appropriate defaults
            for col in df.columns:
                if df[col].dtype in ["float64", "int64"]:
                    df[col] = df[col].fillna(0)
                else:
                    df[col] = df[col].fillna("")
        elif self.null_handling == "flag":
            # Add flag columns for nulls
            for col in df.columns:
                if df[col].isnull().any():
                    df[f"{col}_is_null"] = df[col].isnull()

        stats = {
            "method": self.null_handling,
            "null_counts_before": null_counts_before,
            "total_nulls_found": int(total_nulls)
        }

        return df, stats

    def _remove_duplicates(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Remove duplicate rows.

        Args:
            df: Input DataFrame

        Returns:
            Tuple of (deduplicated DataFrame, deduplication statistics)
        """
        rows_before = len(df)
        df = df.drop_duplicates()
        rows_after = len(df)

        stats = {
            "rows_before": rows_before,
            "rows_after": rows_after,
            "duplicates_removed": rows_before - rows_after
        }

        return df, stats

    def _cast_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cast columns to appropriate types.

        Attempts to infer and cast:
        - Date columns
        - Numeric columns
        - Boolean columns
        """
        for col in df.columns:
            # Try to convert to datetime
            if any(kw in col.lower() for kw in ["date", "time", "created", "updated"]):
                try:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                except Exception:
                    pass

            # Try to convert to numeric
            if df[col].dtype == "object":
                try:
                    numeric_vals = pd.to_numeric(df[col], errors="coerce")
                    if numeric_vals.notna().sum() / len(df) > 0.8:
                        df[col] = numeric_vals
                except Exception:
                    pass

        return df

    def _add_derived_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add derived/computed fields.

        Adds:
        - Processing timestamp
        - Row hash for tracking
        - Partition keys (year, month, day)
        """
        # Add processing timestamp
        df["_processed_at"] = pd.Timestamp.now()

        # Add row hash for deduplication tracking
        df["_row_hash"] = pd.util.hash_pandas_object(df, index=False)

        # Add partition keys from any date column
        date_cols = df.select_dtypes(include=["datetime64"]).columns
        if len(date_cols) > 0:
            primary_date = date_cols[0]
            df["_year"] = df[primary_date].dt.year
            df["_month"] = df[primary_date].dt.month
            df["_day"] = df[primary_date].dt.day

        return df

    def _validate_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Validate the transformed data.

        Returns validation results including:
        - Schema information
        - Data quality metrics
        - Warnings
        """
        warnings = []

        # Check for remaining nulls
        null_cols = df.columns[df.isnull().any()].tolist()
        if null_cols:
            warnings.append(f"Columns with nulls: {null_cols}")

        # Check for potential data quality issues
        for col in df.select_dtypes(include=["object"]).columns:
            unique_ratio = df[col].nunique() / len(df)
            if unique_ratio > 0.9 and len(df) > 100:
                warnings.append(f"Column '{col}' may be a unique identifier (high cardinality)")

        return {
            "is_valid": len(warnings) == 0,
            "row_count": len(df),
            "column_count": len(df.columns),
            "schema": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "warnings": warnings
        }


class TransformationRule:
    """
    Defines a single transformation rule.

    Can be used to create custom transformations.
    """

    def __init__(self, name: str, condition: str, action: str):
        self.name = name
        self.condition = condition
        self.action = action

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply the transformation rule to a DataFrame."""
        # Placeholder for custom rule implementation
        return df
