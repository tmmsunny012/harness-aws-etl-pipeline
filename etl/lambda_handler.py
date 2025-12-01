"""
AWS Lambda Handler for ETL Pipeline
====================================
Main entry point for the Lambda function that orchestrates the ETL process.
"""

import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict

# Handle imports for both Lambda deployment and local development
try:
    # Lambda deployment: src is at root of deployment package
    from src.extract.extractor import DataExtractor
    from src.transform.transformer import DataTransformer
    from src.load.loader import DataLoader
    from src.utils.aws_clients import AWSClients
    from src.utils.config import Config
    from src.utils.metadata import MetadataManager
except ImportError:
    # Local development: imports relative to etl package
    from etl.src.extract.extractor import DataExtractor
    from etl.src.transform.transformer import DataTransformer
    from etl.src.load.loader import DataLoader
    from etl.src.utils.aws_clients import AWSClients
    from etl.src.utils.config import Config
    from etl.src.utils.metadata import MetadataManager

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler function for ETL pipeline.

    Supports multiple trigger types:
    - S3 Event: Triggered when file is uploaded to raw bucket
    - EventBridge: Scheduled execution
    - Direct Invocation: Manual trigger with custom payload

    Args:
        event: Lambda event payload
        context: Lambda context object

    Returns:
        Response dictionary with status and details
    """
    job_id = f"etl-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    start_time = datetime.utcnow()

    logger.info(f"Starting ETL job: {job_id}")
    logger.debug(f"Event: {json.dumps(event, default=str)}")

    # Initialize components
    config = Config()
    aws_clients = AWSClients(config)
    metadata = MetadataManager(aws_clients, config)

    try:
        # Record job start
        metadata.start_job(job_id, event)

        # Determine trigger type and extract source info
        source_info = _parse_event(event)
        logger.info(f"Processing source: {source_info}")

        # Initialize ETL components
        extractor = DataExtractor(aws_clients, config)
        transformer = DataTransformer(config)
        loader = DataLoader(aws_clients, config)

        # EXTRACT
        logger.info("Starting EXTRACT phase...")
        raw_data = extractor.extract(source_info)
        extract_stats = {
            "rows_extracted": len(raw_data) if raw_data is not None else 0,
            "source": source_info
        }
        logger.info(f"Extracted {extract_stats['rows_extracted']} rows")

        # TRANSFORM
        logger.info("Starting TRANSFORM phase...")
        transformed_data, transform_stats = transformer.transform(raw_data)
        logger.info(f"Transformed data: {transform_stats}")

        # LOAD
        logger.info("Starting LOAD phase...")
        load_result = loader.load(transformed_data, job_id)
        logger.info(f"Loaded data to: {load_result['destination']}")

        # Calculate duration
        end_time = datetime.utcnow()
        duration_seconds = (end_time - start_time).total_seconds()

        # Prepare response
        response = {
            "statusCode": 200,
            "body": {
                "job_id": job_id,
                "status": "SUCCESS",
                "duration_seconds": duration_seconds,
                "extract": extract_stats,
                "transform": transform_stats,
                "load": load_result
            }
        }

        # Record job completion
        metadata.complete_job(job_id, response["body"])

        # Send success notification
        aws_clients.send_notification(
            subject=f"ETL Job Success: {job_id}",
            message=json.dumps(response["body"], indent=2, default=str)
        )

        logger.info(f"ETL job completed successfully: {job_id}")
        return response

    except Exception as e:
        error_message = str(e)
        error_traceback = traceback.format_exc()

        logger.error(f"ETL job failed: {error_message}")
        logger.error(error_traceback)

        # Record job failure
        metadata.fail_job(job_id, error_message, error_traceback)

        # Send failure notification
        aws_clients.send_notification(
            subject=f"ETL Job FAILED: {job_id}",
            message=f"Error: {error_message}\n\nTraceback:\n{error_traceback}"
        )

        return {
            "statusCode": 500,
            "body": {
                "job_id": job_id,
                "status": "FAILED",
                "error": error_message
            }
        }


def _parse_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse the incoming event to determine source information.

    Args:
        event: Lambda event payload

    Returns:
        Source information dictionary
    """
    # S3 Event trigger
    if "Records" in event and event["Records"]:
        record = event["Records"][0]
        if "s3" in record:
            return {
                "type": "s3",
                "bucket": record["s3"]["bucket"]["name"],
                "key": record["s3"]["object"]["key"],
                "size": record["s3"]["object"].get("size", 0)
            }

    # EventBridge scheduled event
    if "source" in event and event["source"] == "aws.events":
        return {
            "type": "scheduled",
            "rule": event.get("resources", ["unknown"])[0],
            "time": event.get("time")
        }

    # Direct invocation with custom payload
    if "source_bucket" in event and "source_key" in event:
        return {
            "type": "direct",
            "bucket": event["source_bucket"],
            "key": event["source_key"]
        }

    # Default: process all files in raw bucket
    return {
        "type": "batch",
        "bucket": os.environ.get("S3_RAW_BUCKET", "etl-raw-data"),
        "prefix": event.get("prefix", "")
    }


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        "source_bucket": "etl-raw-data-dev",
        "source_key": "sample/test_data.csv"
    }

    result = handler(test_event, None)
    print(json.dumps(result, indent=2, default=str))
