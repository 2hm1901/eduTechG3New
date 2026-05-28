import json
import os
import re
import secrets
from datetime import datetime, timezone

import boto3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _resolve_user_id(event: dict) -> str:
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    claims = authorizer.get("jwt", {}).get("claims", {}) or authorizer.get("claims", {})
    email = claims.get("email") or claims.get("cognito:username", "")
    if email:
        return email.split("@studybot.local")[0]
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == "x-user-id":
            return value
    return "unknown"


def _extract_doc_id(event: dict) -> str:
    path_params = event.get("pathParameters") or {}
    if path_params.get("doc_id"):
        return path_params["doc_id"]
    path = event.get("path", "")
    match = re.search(r"/api/documents/([^/]+)/chat", path)
    return match.group(1) if match else ""


def _parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _summarize_text(text: str, max_chars: int = 320) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _format_recent_chat(messages: list[dict], limit: int = 6) -> str:
    recent = messages[-limit:]
    if not recent:
        return "No prior conversation."
    return "\n".join(
        f"{'User' if message.get('role') == 'user' else 'Assistant'}: {message.get('content', '').strip()}"
        for message in recent
    )


DOC_CHAT_SYSTEM_PROMPT = """You are a study assistant helping a student understand a specific document.

- Answer ONLY from the provided document context.
- Use prior conversation only to resolve references like "that", "this", or follow-up wording.
- If the document context does not contain the answer, say so plainly.
- Do not use outside knowledge.
- Do not invent details."""


QUERY_REWRITE_SYSTEM_PROMPT = "You rewrite follow-up questions into standalone questions. Output only the rewritten question."


def _build_chat_prompt(memory_summary: str, context: str, question: str) -> str:
    return f"""THREAD MEMORY:
{memory_summary or 'None.'}

DOCUMENT CONTEXT:
{context}

CURRENT QUESTION:
{question}

ANSWER:"""


def _build_rewrite_prompt(recent_history: str, question: str) -> str:
    return f"""Given the conversation history and a follow-up question, rewrite the follow-up as a fully standalone question.

Rules:
- Replace pronouns and references like it, they, this, that, these, those with the explicit concept from history.
- Preserve the user's original intent.
- If the question is already standalone, return it unchanged.
- Return only the standalone question.

{recent_history}

Follow-up question: {question}
Standalone question:"""


def _build_memory_prompt(existing_memory: str, conversation: str) -> str:
    return f"""You are updating compact memory for a document study chat.

Summarize the conversation below into a short factual memory for future turns.

RULES:
- Keep it under 120 words
- Capture only stable context, user intent, and established points
- Do not add facts that were not stated in the chat
- Do not add facts from outside knowledge

EXISTING MEMORY:
{existing_memory or 'None.'}

CONVERSATION:
{conversation}

UPDATED MEMORY:"""


def _should_refresh_memory(message_count: int, has_memory: bool) -> bool:
    if message_count < 20:
        return False
    if not has_memory:
        return True
    return (message_count - 20) % 6 == 0


class DocumentChatStore:
    def __init__(self, table_name: str, region: str):
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def get_document(self, user_id: str, doc_id: str) -> dict | None:
        return self.table.get_item(Key={"user_id": user_id, "sk": f"DOC#{doc_id}"}).get("Item")

    def get_session(self, user_id: str, doc_id: str) -> dict | None:
        item = self.table.get_item(Key={"user_id": user_id, "sk": f"DCHAT#{doc_id}"}).get("Item")
        if not item:
            return None
        return {
            "session_id": item.get("session_id", doc_id),
            "doc_id": item.get("doc_id", doc_id),
            "title": item.get("title", "Document chat"),
            "message_count": int(item.get("message_count", 0)),
            "memory_summary": item.get("memory_summary", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def get_or_create_session(self, user_id: str, doc_id: str, title: str | None = None) -> dict:
        existing = self.get_session(user_id, doc_id)
        if existing:
            return existing
        now = _now()
        self.table.put_item(
            Item={
                "user_id": user_id,
                "sk": f"DCHAT#{doc_id}",
                "session_id": doc_id,
                "doc_id": doc_id,
                "title": title or "Document chat",
                "message_count": 0,
                "memory_summary": "",
                "created_at": now,
                "updated_at": now,
            }
        )
        return self.get_session(user_id, doc_id)

    def list_messages(self, user_id: str, doc_id: str) -> list[dict]:
        resp = self.table.query(
            KeyConditionExpression="user_id = :u AND begins_with(sk, :p)",
            ExpressionAttributeValues={":u": user_id, ":p": f"DCHATMSG#{doc_id}#"},
        )
        items = sorted(resp.get("Items", []), key=lambda item: item.get("created_at", ""))
        return [
            {
                "message_id": item.get("message_id", ""),
                "session_id": item.get("session_id", doc_id),
                "doc_id": item.get("doc_id", doc_id),
                "role": item.get("role", ""),
                "content": item.get("content", ""),
                "citations": item.get("citations", []),
                "created_at": item.get("created_at", ""),
            }
            for item in items
        ]

    def update_session(self, user_id: str, doc_id: str, *, message_count: int | None = None, memory_summary: str | None = None, title: str | None = None) -> dict | None:
        session = self.get_session(user_id, doc_id)
        if not session:
            return None
        now = _now()
        updates = ["updated_at = :updated_at"]
        values = {":updated_at": now}
        names = {}
        if message_count is not None:
            updates.append("message_count = :message_count")
            values[":message_count"] = int(message_count)
        if memory_summary is not None:
            updates.append("memory_summary = :memory_summary")
            updates.append("memory_summary_updated_at = :memory_summary_updated_at")
            values[":memory_summary"] = memory_summary
            values[":memory_summary_updated_at"] = now
        if title is not None:
            updates.append("#title = :title")
            names["#title"] = "title"
            values[":title"] = title
        kwargs = {
            "Key": {"user_id": user_id, "sk": f"DCHAT#{doc_id}"},
            "UpdateExpression": "SET " + ", ".join(updates),
            "ExpressionAttributeValues": values,
        }
        if names:
            kwargs["ExpressionAttributeNames"] = names
        self.table.update_item(**kwargs)
        return self.get_session(user_id, doc_id)

    def add_message(self, user_id: str, doc_id: str, role: str, content: str, citations: list[dict] | None = None) -> dict:
        self.get_or_create_session(user_id, doc_id)
        now = _now()
        message_id = secrets.token_hex(8)
        self.table.put_item(
            Item={
                "user_id": user_id,
                "sk": f"DCHATMSG#{doc_id}#{now}#{message_id}",
                "session_id": doc_id,
                "doc_id": doc_id,
                "message_id": message_id,
                "role": role,
                "content": content[:5000],
                "citations": citations or [],
                "created_at": now,
            }
        )
        messages = self.list_messages(user_id, doc_id)
        title = content[:60] if role == "user" and len(messages) == 1 else None
        self.update_session(user_id, doc_id, message_count=len(messages), title=title)
        return {
            "message_id": message_id,
            "session_id": doc_id,
            "doc_id": doc_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "created_at": now,
        }


class BedrockDocumentChat:
    def __init__(self, region: str, kb_id: str, model_id: str):
        self.runtime = boto3.client("bedrock-runtime", region_name=region)
        self.agent_runtime = boto3.client("bedrock-agent-runtime", region_name=region)
        self.kb_id = kb_id
        self.model_id = model_id

    def retrieve(self, query: str, doc_id: str, top_k: int = 5) -> list[dict]:
        response = self.agent_runtime.retrieve(
            knowledgeBaseId=self.kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": top_k,
                    "filter": {"equals": {"key": "doc_id", "value": doc_id}},
                }
            },
        )
        return [
            {
                "text": item.get("content", {}).get("text", ""),
                "doc_id": item.get("metadata", {}).get("doc_id", doc_id),
                "score": item.get("score", 0.0),
                "metadata": item.get("metadata", {}),
            }
            for item in response.get("retrievalResults", [])
        ]

    def invoke(self, prompt: str, max_tokens: int) -> str:
        response = self.runtime.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )
        return response["output"]["message"]["content"][0]["text"]

    def converse(
        self,
        system_prompt: str,
        user_prompt: str,
        prior_messages: list[dict] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> str:
        messages = []
        for message in prior_messages or []:
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": [{"text": message.get("content", "")}]})
        messages.append({"role": "user", "content": [{"text": user_prompt}]})
        response = self.runtime.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=messages,
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        return response["output"]["message"]["content"][0]["text"]


def _build_citations(chunks: list[dict]) -> list[dict]:
    citations = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata") or {}
        citations.append(
            {
                "doc_id": chunk.get("doc_id", ""),
                "chunk_id": str(metadata.get("chunk_id") or metadata.get("chunk_idx") or f"chunk-{index}"),
                "excerpt": _summarize_text(chunk.get("text", ""), max_chars=320),
            }
        )
    return citations


def _update_memory(store: DocumentChatStore, bedrock: BedrockDocumentChat, user_id: str, doc_id: str, session: dict, messages: list[dict]) -> dict:
    if not _should_refresh_memory(len(messages), bool(session.get("memory_summary"))):
        return session
    conversation = _format_recent_chat(messages, limit=min(12, len(messages)))
    try:
        memory_summary = bedrock.invoke(
            _build_memory_prompt(session.get("memory_summary", ""), conversation),
            max_tokens=180,
        ).strip()
    except Exception:
        memory_summary = " | ".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {_summarize_text(m.get('content', ''), 120)}"
            for m in messages[-6:]
        )
    return store.update_session(user_id, doc_id, memory_summary=memory_summary, message_count=len(messages)) or session


def _reformulate_query(bedrock: BedrockDocumentChat, recent_messages: list[dict], question: str) -> str:
    if not recent_messages:
        return question
    history = _format_recent_chat(recent_messages, limit=6)
    try:
        rewritten = bedrock.converse(
            QUERY_REWRITE_SYSTEM_PROMPT,
            _build_rewrite_prompt(history, question),
            max_tokens=120,
            temperature=0,
        ).strip()
        return rewritten or question
    except Exception:
        return question


def _handle_get(event: dict, store: DocumentChatStore, user_id: str, doc_id: str) -> dict:
    document = store.get_document(user_id, doc_id)
    if not document:
        return _response(404, {"error": "Document not found"})
    session = store.get_or_create_session(user_id, doc_id, title=document.get("filename", "Document chat"))
    messages = store.list_messages(user_id, doc_id)
    session = store.update_session(user_id, doc_id, message_count=len(messages)) or session
    return _response(200, {"session": session, "messages": messages})


def _handle_post(event: dict, store: DocumentChatStore, bedrock: BedrockDocumentChat, user_id: str, doc_id: str) -> dict:
    document = store.get_document(user_id, doc_id)
    if not document:
        return _response(404, {"error": "Document not found"})
    payload = _parse_body(event)
    message = (payload.get("message") or "").strip()
    if not message:
        return _response(400, {"error": "Message is required"})

    session = store.get_or_create_session(user_id, doc_id, title=document.get("filename", "Document chat"))
    existing_messages = store.list_messages(user_id, doc_id)
    user_message = store.add_message(user_id, doc_id, "user", message)

    effective_query = _reformulate_query(bedrock, existing_messages, message)
    chunks = bedrock.retrieve(effective_query, doc_id, top_k=5)
    citations = _build_citations(chunks)
    context = "\n\n".join(f"[chunk {index}] {chunk['text']}" for index, chunk in enumerate(chunks, start=1))

    if not context.strip():
        answer = "I can't answer that from this document because I couldn't find supporting content."
        citations = []
    else:
        try:
            answer = bedrock.converse(
                DOC_CHAT_SYSTEM_PROMPT,
                _build_chat_prompt(session.get("memory_summary", ""), context, message),
                prior_messages=existing_messages[-6:],
                max_tokens=512,
                temperature=0.2,
            )
        except Exception as exc:
            print("chat invoke failed:", exc)
            answer = "AI is currently unavailable. Please try again later."

    assistant_message = store.add_message(user_id, doc_id, "assistant", answer, citations)
    all_messages = existing_messages + [user_message, assistant_message]
    session = _update_memory(store, bedrock, user_id, doc_id, session, all_messages)
    session = store.update_session(user_id, doc_id, message_count=len(all_messages)) or session
    return _response(
        200,
        {
            "session": session,
            "user_message": user_message,
            "assistant_message": assistant_message,
        },
    )


def lambda_handler(event, context):
    try:
        region = os.environ.get("REGION", "ap-southeast-2")
        table_name = os.environ["DYNAMODB_TABLE"]
        kb_id = os.environ["BEDROCK_KB_ID"]
        model_id = os.environ.get("BEDROCK_MODEL_ARN") or os.environ.get("BEDROCK_MODEL_ID", "")
        if not model_id:
            return _response(500, {"error": "Bedrock model is not configured"})

        doc_id = _extract_doc_id(event)
        if not doc_id:
            return _response(400, {"error": "doc_id is required"})

        user_id = _resolve_user_id(event)
        store = DocumentChatStore(table_name, region)
        bedrock = BedrockDocumentChat(region, kb_id, model_id)

        method = (event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "GET")).upper()
        path = event.get("path", "")

        if method == "GET" and path.endswith("/chat"):
            return _handle_get(event, store, user_id, doc_id)
        if method == "POST" and path.endswith("/chat/messages"):
            return _handle_post(event, store, bedrock, user_id, doc_id)
        return _response(404, {"error": "Not found"})
    except Exception as exc:
        print("chat lambda error:", exc)
        return _response(500, {"error": str(exc)})
