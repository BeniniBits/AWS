# AWS
Code for managing an AWS infrastructure

- S3 Glacier Object Restoration Tool
[restore_s3_glacier.py](https://github.com/BeniniBits/AWS/blob/main/restore_s3_glacier.py)

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
