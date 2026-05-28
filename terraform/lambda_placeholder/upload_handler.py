import base64
import json
import os
import re
import uuid

import boto3
from botocore.config import Config


def _make_s3_client():
    region = os.environ.get("REGION") or "ap-southeast-2"
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(signature_version="s3v4"),
    )


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _resolve_user_id(event):
    ctx = event.get("requestContext", {})
    claims = ctx.get("authorizer", {}).get("claims", {})
    if not claims:
        claims = ctx.get("authorizer", {}).get("jwt", {}).get("claims", {})
    email = claims.get("email") or claims.get("cognito:username") or "anonymous"
    if "@studybot.local" in email:
        email = email.split("@", 1)[0]
    return re.sub(r"[^a-zA-Z0-9_-]", "_", email)


def lambda_handler(event, context):
    bucket = os.environ.get("PDF_BUCKET_NAME")
    if not bucket:
        return _response(500, {"error": "PDF_BUCKET_NAME is not configured"})

    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = json.loads(base64.b64decode(body).decode("utf-8"))
    else:
        body = json.loads(body)

    filename = (body.get("filename") or "upload.bin").strip()
    if not filename:
        return _response(400, {"error": "filename is required"})

    content_type = (body.get("contentType") or "application/octet-stream").strip()
    user_id = _resolve_user_id(event)
    doc_id = str(uuid.uuid4())
    key = f"{user_id}/{doc_id}/{filename}"

    upload_url = _make_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=900,
    )

    return _response(
        200,
        {
            "uploadUrl": upload_url,
            "key": key,
            "docId": doc_id,
            "bucket": bucket,
        },
    )
