"""
S3 Glacier Object Restoration Tool
This script automates the process of restoring objects from S3 Glacier Flexible Retrieval
storage class and optionally moving them to another storage class or bucket. It can process
all objects in a specified bucket, identifying those in Glacier storage, initiating restoration
requests, and optionally copying restored objects to a new storage class.
Features:
- Initiates restore requests for Glacier objects
- Configurable restoration period and retrieval tier
- Optional migration of restored objects to different storage class
- Optional copying to another bucket
- Comprehensive logging to file and/or console
- Dry-run mode for testing without making changes
Requirements:
- boto3
- Valid AWS credentials with appropriate S3 permissions
Usage Examples:
    # Restore all Glacier objects with default settings (7 days, Standard tier)
    python restore_s3_glacier.py --bucket my-bucket --region us-east-1
    # Restore with custom settings and move to STANDARD_IA
    python restore_s3_glacier.py --bucket my-bucket --region us-east-1 --restore-days 10 \
        --retrieval-tier Bulk --storage-class STANDARD_IA
    # Restore and copy to another bucket
    python restore_s3_glacier.py --bucket my-bucket --region us-east-1 \
        --destination-bucket my-other-bucket --storage-class STANDARD
    # Dry run to see what would happen without making changes
    python restore_s3_glacier.py --bucket my-bucket --region us-east-1 --dry-run
Note:
    The script tracks the state of restoration processes. Objects with ongoing restore
    requests will be logged but not modified. Already restored objects will be copied
    to the target storage class if specified.

Original version by Davide Benini https://github.com/BeniniBits, 2025
"""

import boto3
import argparse
import logging
from botocore.exceptions import ClientError

# Function to setup logging
def setup_logging(log_file: str = None):
    """
    Configure logging for both console and file output.
    This function sets up Python's logging system to output log messages to the console
    and optionally to a file. The logging level is set to INFO.
    Args:
        log_file (str, optional):
            Path to the log file. If provided, logs will be written
            to this file in addition to the console. Defaults to None.
    Returns:
        None
    Example:
        >>> setup_logging()  # Console logging only
        >>> setup_logging("app.log")  # Console and file logging
    """

    handlers = []
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    handlers.append(logging.StreamHandler())
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers
    )

def parse_args():
    """
    Parse command line arguments for the S3 Glacier object restoration tool.

    This function sets up the argument parser with all needed parameters for
    restoring objects from S3 Glacier Flexible Retrieval, with options to
    specify restoration details and optionally copy objects to different
    storage classes or buckets.

    Returns:
        argparse.Namespace: An object containing all the parsed command line arguments:
            - bucket (str): Source S3 bucket name
            - region (str): AWS region
            - restore_days (int): Number of days to keep restored objects (default: 7)
            - retrieval_tier (str): Retrieval tier for Glacier restore (default: 'Standard')
            - storage_class (str, optional): Target storage class if copying objects
            - destination_bucket (str, optional): Destination bucket if copying objects
            - log_file (str, optional): Path to the log file
            - dry_run (bool): Flag to simulate actions without making changes
    """

    # defaults
    default_restore_days = 7
    default_retrieval_tier = 'Standard'

    parser = argparse.ArgumentParser(description="Restore S3 Glacier Flexible Retrieval objects and optionally move them to another storage class.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--bucket', required=True, help='Source S3 bucket name')
    parser.add_argument('--region', required=True, help='AWS region')
    parser.add_argument('--restore-days', type=int, default=default_restore_days, help=f'Number of days to keep restored objects (default: {default_restore_days})')
    parser.add_argument('--retrieval-tier', default=default_retrieval_tier, choices=['Standard', 'Bulk', 'Expedited'], help=f'Retrieval tier for Glacier restore (default: {default_retrieval_tier})')
    parser.add_argument('--storage-class', help='Target storage class (e.g., STANDARD, GLACIER_IR). \nIf not provided, objects will only be restored without copying.')
    parser.add_argument('--destination-bucket', help='Optional destination bucket to copy restored objects. \nIf not provided, objects will be copied to the source bucket overwriting the original.')
    parser.add_argument('--log-file', help='Path to the log file. \nIf not provided, log messages will only be displayed on screen.')
    parser.add_argument('--dry-run', action='store_true', help='Simulate actions without making changes to S3')
    return parser.parse_args()

def restore_object(s3_client: boto3.client, bucket: str, key: str, restore_days: int, retrieval_tier: str, dry_run: bool):
    """
    Initiates a restore request for an S3 object stored in Glacier.

    This function attempts to restore an object from S3 Glacier storage. If dry_run 
    is enabled, it will only log the intended action without performing it.

    Args:
        s3_client (boto3.client): The boto3 S3 client instance.
        bucket (str): The name of the S3 bucket.
        key (str): The key/path of the object to restore.
        restore_days (int): Number of days the restored object will be available.
        retrieval_tier (str): Glacier retrieval tier (e.g., 'Standard', 'Bulk', 'Expedited').
        dry_run (bool): If True, only logs the action without performing it.

    Raises:
        ClientError: When AWS S3 operations fail, specific error codes are handled:
            - 'RestoreAlreadyInProgress': Logged as warning
            - 'InvalidObjectState': Logged as warning (object not in Glacier)
            - Other errors: Logged as errors with stack trace

    Returns:
        None
    """

    if dry_run:
        logging.info(f"[Dry-run] Would initiate restore for: {key}")
        return
    try:
        s3_client.restore_object(
            Bucket=bucket,
            Key=key,
            RestoreRequest={
                'Days': restore_days,
                'GlacierJobParameters': {'Tier': retrieval_tier}
            }
        )
        logging.info(f"Restore initiated for: {key}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
            logging.warning(f"Restore already in progress for: {key}")
        elif e.response['Error']['Code'] == 'InvalidObjectState':
            logging.warning(f"Object not in Glacier Flexible Retrieval: {key}")
        else:
            logging.error(f"Error restoring {key}: {e}", exc_info=True)

def copy_object(s3_client: boto3.client, source_bucket: str, key: str, destination_bucket: str, storage_class: str, dry_run: bool):
    """
    Copy an S3 object to a destination bucket with a specified storage class.

    This function copies an object from a source S3 bucket to a destination bucket
    while allowing you to change its storage class. If no destination bucket is provided,
    the object is copied within the same bucket (effectively changing only its storage class).

    Args:
        s3_client (boto3.client): An initialized boto3 S3 client
        source_bucket (str): The name of the source bucket
        key (str): The key (path) of the object to copy
        destination_bucket (str): The name of the destination bucket. If None or empty,
                                  the source bucket will be used
        storage_class (str): The storage class to apply to the copied object
                             (e.g., 'STANDARD', 'GLACIER', 'DEEP_ARCHIVE')
        dry_run (bool): If True, simulates the operation without performing actual copy

    Returns:
        None

    Raises:
        ClientError: If an error occurs during the S3 copy operation
    """
    
    target_bucket = destination_bucket if destination_bucket else source_bucket
    if dry_run:
        logging.info(f"[Dry-run] Would copy {key} from {source_bucket} to {target_bucket} with storage class {storage_class}")
        return
    try:
        s3_client.copy_object(
            Bucket=target_bucket,
            CopySource={'Bucket': source_bucket, 'Key': key},
            Key=key,
            StorageClass=storage_class,
            MetadataDirective='COPY'
        )
        logging.info(f"Copied {key} to bucket {target_bucket} with storage class {storage_class}")
    except ClientError as e:
        logging.error(f"Error copying {key}: {e}", exc_info=True)

def main():
    """
    Main function to restore objects from S3 Glacier and optionally copy them to
    another bucket or storage class.
    
    The function processes all objects in the specified bucket, checking for Glacier
    objects and handling them based on their current restore status:
    - For objects with completed restoration, copies them to the destination bucket 
      with the specified storage class if provided
    - For objects with ongoing restoration, logs the progress
    - For objects not yet restored, initiates restoration with the specified parameters
    
    All operations are performed according to the command line arguments parsed by
    parse_args(), including dry-run mode which logs actions without executing them.
    
    Errors during object processing are caught and logged without interrupting the
    overall operation.
    
    Returns:
        None
    """
    
    args = parse_args()
    setup_logging(args.log_file)
    s3 = boto3.client('s3', region_name=args.region)

    paginator = s3.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=args.bucket)

    for page in page_iterator:
        for obj in page.get('Contents', []):
            key = obj['Key']
            try:
                head = s3.head_object(Bucket=args.bucket, Key=key)
                storage_class = head.get('StorageClass', 'STANDARD')

                if storage_class == 'GLACIER':
                    restore_status = head.get('Restore', '')
                    if 'ongoing-request="false"' in restore_status:
                        if args.storage_class:
                            copy_object(s3, args.bucket, key, args.destination_bucket, args.storage_class, args.dry_run)
                        else:
                            logging.info(f"Object already restored (skipping copy as --storage-class not provided): {key}")
                    elif 'ongoing-request="true"' in restore_status:
                        logging.info(f"Restore in progress for: {key}")
                    else:
                        restore_object(s3, args.bucket, key, args.restore_days, args.retrieval_tier, args.dry_run)
            except ClientError as e:
                logging.error(f"Error processing object {key}: {e}", exc_info=True)

if __name__ == '__main__':
    main()
