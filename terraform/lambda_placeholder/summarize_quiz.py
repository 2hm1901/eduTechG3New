import json
import os
import re
import boto3

QUIZ_PROMPT_TEMPLATE = """You are a study assistant. Based on the study content below, generate exactly {question_count} multiple-choice quiz questions.

RULES:
- Each question must have exactly 4 options labeled A, B, C, D.
- Exactly one option is correct.
- Questions should test understanding, not just memorisation.
- Cover different parts of the content.

Return your answer as a JSON array with this exact structure (no markdown fences, just raw JSON):
[
  {{
    "id": 1,
    "question": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..." }},
    "answer": "A",
    "explanation": "Short explanation why this is correct."
  }}
]

STUDY CONTENT:
{content}
"""

def _resolve_user_id(event: dict) -> str:
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    claims = authorizer.get("jwt", {}).get("claims", {})
    if not claims:
        claims = authorizer.get("claims", {})
    email = claims.get("email") or claims.get("cognito:username", "")
    if email:
        if "@studybot.local" in email:
            return email.split("@")[0]
        return email
    headers = event.get("headers", {})
    for k, v in headers.items():
        if k.lower() == "x-user-id":
            return v
    return "unknown"

def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._/-]", "_", value)

def _build_source_key(source_key: str) -> str:
    base = source_key.rsplit(".", 1)[0]
    base = _safe_key(base)
    return f"source/{base}.txt"

def _invoke_bedrock(content: str, question_count: int, region: str, model_id: str) -> str:
    bedrock = boto3.client("bedrock-runtime", region_name=region)
    prompt = QUIZ_PROMPT_TEMPLATE.format(content=content[:15000], question_count=question_count)
    
    if "anthropic.claude" in model_id:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        })
    else:
        # Generic fallback
        body = json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {"maxTokenCount": 2048, "temperature": 0.5}
        })

    response = bedrock.invoke_model(
        modelId=model_id,
        body=body,
        accept="application/json",
        contentType="application/json"
    )
    
    response_body = json.loads(response.get("body").read())
    
    if "anthropic.claude" in model_id:
        return response_body["content"][0]["text"]
    else:
        return response_body.get("results", [{}])[0].get("outputText", "")

def _parse_json_array(raw: str) -> list:
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    elif cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, list) else []
    except Exception:
        # Fallback to finding JSON array via regex
        match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        doc_id = body.get("doc_id")
        if not doc_id:
            return {"statusCode": 400, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": "doc_id is required"})}
            
        region = os.environ.get("REGION", "ap-southeast-2")
        user_id = _resolve_user_id(event)
        
        dynamodb = boto3.resource("dynamodb", region_name=region)
        table = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
        resp = table.get_item(Key={"user_id": user_id, "sk": f"DOC#{doc_id}"})
        item = resp.get("Item")
        
        if not item:
            return {"statusCode": 404, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": "Document not found"})}
            
        filename = item.get("filename", "")
        source_key = f"{user_id}/{doc_id}/{filename}"
        source_key_out = _build_source_key(source_key)
        
        s3 = boto3.client("s3", region_name=region)
        try:
            obj = s3.get_object(Bucket=os.environ["SOURCE_BUCKET_NAME"], Key=source_key_out)
            text = obj["Body"].read().decode("utf-8")
        except Exception as e:
            return {"statusCode": 404, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": f"Extracted text not found. The document might still be processing. Error: {str(e)}"})}
            
        if not text.strip():
            return {"statusCode": 400, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"error": "Extracted text is empty."})}
            
        try:
            raw = _invoke_bedrock(text, 10, region, os.environ["BEDROCK_MODEL_ID"])
            quiz = _parse_json_array(raw)
        except Exception as e:
            print("Failed to generate quiz:", e)
            quiz = [{
                "id": 1,
                "question": "Failed to generate quiz. Please try again later.",
                "options": {"A": "Ok", "B": "Cancel", "C": "Retry", "D": "Exit"},
                "answer": "A",
                "explanation": "The AI encountered an error."
            }]
            
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"quiz": quiz})
        }
    except Exception as e:
        print("Error:", e)
        return {
            "statusCode": 500,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)})
        }
