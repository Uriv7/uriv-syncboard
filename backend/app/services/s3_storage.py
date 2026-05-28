import boto3
import uuid
import os
import logging

log = logging.getLogger("syncboard.s3")
_s3 = None

def get_s3():
    global _s3
    if _s3 is None:
        region = os.environ.get("AWS_REGION", "ap-south-1")
        _s3 = boto3.client("s3", region_name=region)
    return _s3

def upload_image(png_bytes: bytes, session_id: str) -> str:
    bucket = os.environ["S3_BUCKET"]
    key = f"sessions/{session_id}/{uuid.uuid4()}.png"
    try:
        get_s3().put_object(
            Bucket=bucket,
            Key=key,
            Body=png_bytes,
            ContentType="image/png"
        )
        url = get_s3().generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=86400
        )
        log.info(f"Image uploaded and presigned URL generated: {key}")
        return url
    except Exception as e:
        log.error(f"S3 operations failed: {e}")
        return ""
