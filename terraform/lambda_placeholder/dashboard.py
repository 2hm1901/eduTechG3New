import json
import os

import boto3
from boto3.dynamodb.conditions import Key


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-User-Id",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body),
    }


def _resolve_user_id(event: dict) -> str:
    headers = event.get("headers") or {}
    lower_headers = {str(k).lower(): v for k, v in headers.items()}
    if lower_headers.get("x-user-id"):
        return str(lower_headers["x-user-id"]).strip()

    authorizer = ((event.get("requestContext") or {}).get("authorizer") or {})
    jwt_claims = ((authorizer.get("jwt") or {}).get("claims") or {})
    claims = jwt_claims or (authorizer.get("claims") or {})
    email = claims.get("email") or claims.get("cognito:username") or ""
    if email:
        return email.split("@")[0]

    params = event.get("queryStringParameters") or {}
    if params.get("user_id"):
        return str(params["user_id"]).strip()

    return ""


def _parse_topics(raw_topics) -> list[dict]:
    if not raw_topics:
        return []
    if isinstance(raw_topics, list):
        return raw_topics
    if isinstance(raw_topics, str):
        try:
            data = json.loads(raw_topics)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _document_status(doc: dict) -> str:
    has_summary = bool(doc.get("doc_summary"))
    has_topics = bool(doc.get("topics"))
    if has_summary and has_topics:
        return "ready"
    if has_summary:
        return "summary_ready"
    if has_topics:
        return "topics_ready"
    return "uploaded"


def lambda_handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _json_response(200, {"ok": True})

    user_id = _resolve_user_id(event)
    if not user_id:
        return _json_response(401, {"detail": "Unauthorized"})

    table_name = os.getenv("USERSTORE_TABLE", "ai-study-buddy-main-v2")
    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"))
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    response = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("sk").begins_with("DOC#"),
        ScanIndexForward=False,
    )
    items = response.get("Items", [])

    documents = []
    total_topics = 0
    summaries_ready = 0
    pending_analysis = 0

    for item in items:
        topics = _parse_topics(item.get("doc_topics"))
        if item.get("doc_summary"):
            summaries_ready += 1
        if not item.get("doc_summary") and not topics:
            pending_analysis += 1
        total_topics += len(topics)

        document = {
            "doc_id": item.get("doc_id", ""),
            "filename": item.get("filename", ""),
            "created_at": item.get("created_at", ""),
            "size": int(item.get("size", 0) or 0),
            "chars": int(item.get("chars", 0) or 0),
            "location": item.get("location", ""),
            "mime_type": item.get("mime_type", ""),
            "doc_summary": item.get("doc_summary", ""),
            "summary_generated_at": item.get("summary_generated_at", ""),
            "topics_generated_at": item.get("topics_generated_at", ""),
            "topics": topics,
        }
        document["status"] = _document_status(document)
        documents.append(document)

    dashboard = {
        "user_id": user_id,
        "total_documents": len(documents),
        "summaries_ready": summaries_ready,
        "topics_ready": total_topics,
        "pending_analysis": pending_analysis,
        "documents": documents,
        "quiz_history": [],
    }
    return _json_response(200, dashboard)
