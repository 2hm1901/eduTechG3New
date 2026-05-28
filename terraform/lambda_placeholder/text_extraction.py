import io
import json
import os
import re
import urllib.parse

import boto3


def _get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._/-]", "_", value)


def _extract_text(filename: str, payload: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(payload))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    try:
        return payload.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _build_source_key(source_key: str) -> str:
    base = source_key.rsplit(".", 1)[0]
    base = _safe_key(base)
    return f"source/{base}.txt"


def lambda_handler(event, context):
    region = os.environ.get("REGION") or os.environ.get("AWS_REGION") or "ap-southeast-2"
    source_bucket = _get_env("SOURCE_BUCKET_NAME")
    kb_id = _get_env("BEDROCK_KB_ID")
    datasource_id = _get_env("BEDROCK_DATASOURCE_ID")

    s3 = boto3.client("s3", region_name=region)
    bedrock = boto3.client("bedrock-agent", region_name=region)

    records = event.get("Records", [])
    processed = 0
    for record in records:
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        key = record.get("s3", {}).get("object", {}).get("key")
        if not bucket or not key:
            continue
        source_key = urllib.parse.unquote_plus(key)
        if source_key.lower().endswith("/"):
            continue

        obj = s3.get_object(Bucket=bucket, Key=source_key)
        data = obj["Body"].read()
        text = _extract_text(source_key, data).strip()
        if not text:
            continue

        source_key_out = _build_source_key(source_key)
        s3.put_object(
            Bucket=source_bucket,
            Key=source_key_out,
            Body=text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        processed += 1

    if processed:
        bedrock.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=datasource_id,
            description=f"Source ingestion ({processed} objects)",
        )

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": processed}),
    }
