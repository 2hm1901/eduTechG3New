"""Endpoint handlers for the Bank -> Folder workspace flow."""
import io
import json
import re
import uuid
from collections import Counter
from urllib.parse import urlparse


PROMPT_TEMPLATE = """You are a study assistant. Answer the student's question using ONLY the
context retrieved from their uploaded lecture notes. Cite the source by chunk
number where possible. If the context does not contain the answer, say so
plainly. Do not invent information.

CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""

TOPIC_PROMPT_TEMPLATE = """You are a study assistant. Read the folder content and generate exactly 5 study topics.

Return raw JSON only, no markdown:
[
  {{
    "title": "Topic title",
    "summary": "2-3 sentence study guide summary"
  }}
]

FOLDER CONTENT:
{content}
"""

QUIZ_PROMPT_TEMPLATE = """You are a study assistant. Based on the study content below, generate exactly {question_count} multiple-choice quiz questions.

RULES:
- Each question must have exactly 4 options.
- The options dictionary MUST use EXACTLY the keys "A", "B", "C", and "D". Do not use any other letters or numbers.
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

TOPIC_CHAT_PROMPT_TEMPLATE = """You are a study assistant helping inside a workspace for the topic "{topic_title}".

Topic study guide:
{topic_summary}

Use the retrieved lecture context below when answering. Keep the answer grounded and mention when context is weak.

CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""

DOC_SUMMARY_PROMPT = """You are a study assistant. Read the document content below and write a concise study summary.

RULES:
- Keep it brief: 120-180 words total
- Focus only on the most important concepts
- Use 3-5 short bullet points
- End with a one-sentence takeaway
- Write clearly for a student revising quickly
- Do NOT invent information

DOCUMENT CONTENT:
{content}

CONCISE SUMMARY:"""

DOC_TESTABLE_CONCEPTS_PROMPT = """You are a study assistant. Read the document content below and identify the FIVE MOST TESTABLE CONCEPTS — ideas that are most likely to appear on an exam or quiz.

Return raw JSON only, no markdown fences:
[
  {{
    "title": "Concept title",
    "why_testable": "1-2 sentences explaining why this is likely to be tested",
    "key_points": ["point 1", "point 2", "point 3"]
  }}
]

DOCUMENT CONTENT:
{content}

FIVE MOST TESTABLE CONCEPTS:"""

DOC_TOPICS_PROMPT = """You are a study assistant. Read the document content below and generate exactly 5 study topics for this single document.

Return raw JSON only, no markdown:
[
  {{
    "title": "Topic title",
    "summary": "2-3 sentence study guide summary"
  }}
]

DOCUMENT CONTENT:
{content}

FIVE STUDY TOPICS:"""

DOC_CHAT_SYSTEM_PROMPT = """You are a study assistant helping a student understand a specific document.

Rules:
- Answer ONLY from the provided document context.
- Use prior conversation only to resolve references like "that", "this", or follow-up wording.
- If the document context does not contain the answer, say so plainly.
- Do not use outside knowledge.
- Do not invent details."""

DOC_CHAT_PROMPT = """THREAD MEMORY:
{memory_summary}

DOCUMENT CONTEXT:
{context}

CURRENT QUESTION:
{question}

ANSWER:"""

DOC_CHAT_MEMORY_PROMPT = """You are updating compact memory for a document study chat.

Summarize the conversation below into a short factual memory for future turns.

RULES:
- Keep it under 120 words
- Capture only stable context, user intent, and established points
- Do not add facts that were not stated in the chat
- Do not add facts from outside knowledge

EXISTING MEMORY:
{existing_memory}

CONVERSATION:
{conversation}

UPDATED MEMORY:"""

DOC_CHAT_REWRITE_SYSTEM_PROMPT = "You rewrite follow-up questions into standalone questions. Output only the rewritten question."

DOC_CHAT_REWRITE_PROMPT = """Given the conversation history and a follow-up question, rewrite the follow-up as a fully standalone question.

Rules:
- Replace pronouns and references like it, they, this, that, these, those with the explicit concept from history.
- Preserve the user's original intent.
- If the question is already standalone, return it unchanged.
- Return only the standalone question.

Conversation history:
{history}

Follow-up question: {question}
Standalone question:"""

STOPWORDS = {
    "about", "after", "again", "against", "also", "because", "before", "being", "between", "could",
    "each", "from", "have", "into", "lecture", "notes", "only", "other", "should", "their", "there",
    "these", "those", "through", "under", "using", "what", "when", "where", "which", "with", "would",
    "your", "this", "that", "they", "them", "then", "than", "such", "over", "while", "slide",
    "slides", "topic", "topics", "study", "students", "student", "content", "document",
}


def _extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return "(pypdf not installed — install requirements.txt)"
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text)]


def _title_from_text(text: str, fallback: str) -> str:
    words = [word for word in _tokenize(text) if word not in STOPWORDS]
    common = [word.title() for word, _ in Counter(words).most_common(3)]
    return " ".join(common) if common else fallback


def _summarize_text(text: str, max_chars: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _split_topic_segments(doc_texts: list[dict], count: int = 5) -> list[dict]:
    segments = []
    for doc in doc_texts:
        sentences = re.split(r"(?<=[.!?])\s+", doc["text"])
        bucket = []
        for sentence in sentences:
            if len(" ".join(bucket)) + len(sentence) < 500:
                bucket.append(sentence)
            else:
                segment = " ".join(bucket).strip()
                if segment:
                    segments.append({"doc_id": doc["doc_id"], "text": segment})
                bucket = [sentence]
        segment = " ".join(bucket).strip()
        if segment:
            segments.append({"doc_id": doc["doc_id"], "text": segment})
    if not segments:
        return []
    if len(segments) <= count:
        return segments
    step = max(1, len(segments) // count)
    selected = []
    for index in range(0, len(segments), step):
        selected.append(segments[index])
        if len(selected) == count:
            break
    return selected


def _parse_json_array(raw: str) -> list:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])
    data = json.loads(cleaned)
    return data if isinstance(data, list) else []


def _fallback_topics(doc_texts: list[dict], count: int = 5) -> list[dict]:
    segments = _split_topic_segments(doc_texts, count=count)
    topics = []
    for index, segment in enumerate(segments, start=1):
        title = _title_from_text(segment["text"], f"Topic {index}")
        topics.append(
            {
                "title": title,
                "summary": _summarize_text(segment["text"]),
                "source_doc_ids": [segment["doc_id"]],
            }
        )
    while len(topics) < count:
        index = len(topics) + 1
        topics.append(
            {
                "title": f"Topic {index}",
                "summary": "Local fallback topic generated from the folder content. Add richer source material for better topic quality.",
                "source_doc_ids": [doc["doc_id"] for doc in doc_texts[:1]],
            }
        )
    return topics[:count]


def _fallback_quiz(topic_title: str, topic_summary: str, question_count: int) -> list[dict]:
    keywords = [word.title() for word in _tokenize(topic_summary) if word not in STOPWORDS]
    keywords = list(dict.fromkeys(keywords))[: max(4, question_count + 2)]
    if len(keywords) < 4:
        keywords.extend(["Concept", "Evidence", "Practice", "Review"])
    quiz = []
    for index in range(question_count):
        correct = keywords[index % len(keywords)]
        distractors = []
        for word in keywords:
            if word != correct and word not in distractors:
                distractors.append(word)
            if len(distractors) == 3:
                break
        options = {"A": correct, "B": distractors[0], "C": distractors[1], "D": distractors[2]}
        quiz.append(
            {
                "id": index + 1,
                "question": f"Which concept is most closely associated with the topic '{topic_title}'?",
                "options": options,
                "answer": "A",
                "explanation": f"{correct} appears in the topic study guide and is treated as a key idea in this local fallback quiz.",
            }
        )
    return quiz


def _get_doc_text(user_id: str, doc_id: str, vector_store) -> str:
    if hasattr(vector_store, "docs"):
        matched = [text for (_cid, text, md) in vector_store.docs if md.get("doc_id") == doc_id]
        if matched:
            return "\n\n".join(matched)
    chunks = vector_store.search("summary overview key concepts", top_k=50, filter={"doc_id": doc_id})
    if chunks:
        return "\n\n".join(chunk["text"] for chunk in chunks)
    return ""


def _build_source_text_key_from_location(location: str) -> str:
    parsed = urlparse(location or "")
    if parsed.scheme != "s3" or not parsed.path:
        return ""
    source_key = parsed.path.lstrip("/")
    base = re.sub(r"[^A-Za-z0-9._/-]", "_", source_key.rsplit(".", 1)[0])
    return f"source/{base}.txt"


def _load_source_text(document: dict | None) -> str:
    if not document:
        return ""
    source_key = _build_source_text_key_from_location(document.get("location", ""))
    if not source_key:
        return ""
    try:
        import boto3
        from src.config import config

        if not config.source_bucket_name:
            return ""
        s3 = boto3.client("s3", region_name=config.aws_region)
        obj = s3.get_object(Bucket=config.source_bucket_name, Key=source_key)
        return obj["Body"].read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _get_doc_text_with_fallback(user_id: str, doc_id: str, vector_store, userstore) -> str:
    text = _get_doc_text(user_id, doc_id, vector_store)
    if text.strip():
        return text
    if hasattr(userstore, "get_document"):
        fallback_text = _load_source_text(userstore.get_document(user_id, doc_id))
        if fallback_text.strip():
            return fallback_text
    return ""


def _get_folder_doc_texts(user_id: str, folder_id: str, userstore, vector_store) -> list[dict]:
    docs = userstore.get_folder_docs(user_id, folder_id)
    results = []
    for doc in docs:
        text = _get_doc_text_with_fallback(user_id, doc["doc_id"], vector_store, userstore)
        if text:
            results.append({"doc_id": doc["doc_id"], "filename": doc["filename"], "text": text})
    return results


def handle_upload(user_id: str, filename: str, data: bytes, storage, userstore, vector_store) -> dict:
    doc_id = str(uuid.uuid4())
    key = f"{user_id}/{doc_id}/{filename}"
    location = storage.put(key, data)
    text = _extract_text(filename, data)
    if text.strip():
        vector_store.ingest(doc_id=doc_id, text=text, metadata={"user_id": user_id, "filename": filename})
    userstore.add_doc(
        user_id=user_id,
        doc_id=doc_id,
        metadata={
            "filename": filename,
            "size": len(data),
            "location": location,
            "chars": len(text),
            "mime_type": "",
        },
    )
    return {
        "doc_id": doc_id,
        "filename": filename,
        "size": len(data),
        "chars_extracted": len(text),
        "location": location,
    }


def handle_presign(user_id: str, filename: str, content_type: str, storage) -> dict:
    doc_id = str(uuid.uuid4())
    key = f"{user_id}/{doc_id}/{filename}"
    upload_url = storage.generate_presigned_url(key, content_type)
    return {
        "upload_url": upload_url,
        "key": key,
        "doc_id": doc_id,
    }


def handle_finalize(user_id: str, doc_id: str, filename: str, key: str, size: int, storage, userstore, vector_store) -> dict:
    # 1. Get location from storage
    if hasattr(storage, "bucket"):
        location = f"s3://{storage.bucket}/{key}"
    else:
        location = f"file://{storage.base.resolve()}/{key}"

    # 2. Extract text from storage
    data = storage.get(key)
    text = _extract_text(filename, data)

    # 3. Ingest and Add Doc
    if text.strip():
        vector_store.ingest(doc_id=doc_id, text=text, metadata={"user_id": user_id, "filename": filename})
    userstore.add_doc(
        user_id=user_id,
        doc_id=doc_id,
        metadata={
            "filename": filename,
            "size": size,
            "location": location,
            "chars": len(text),
            "mime_type": "",
        },
    )
    return {
        "doc_id": doc_id,
        "filename": filename,
        "size": size,
        "chars_extracted": len(text),
        "location": location,
    }


def handle_direct_upload(key: str, data: bytes, storage) -> dict:
    """Used for local development only to simulate S3 PUT."""
    storage.put(key, data)
    return {"status": "ok"}


def handle_list_docs(user_id: str, userstore) -> dict:
    return {"user_id": user_id, "docs": userstore.list_docs(user_id)}


def handle_register(username: str, password: str, userstore) -> dict:
    if not username or not password:
        return {"error": "Username and password are required"}
    if len(username) < 3:
        return {"error": "Username must be at least 3 characters"}
    if len(password) < 4:
        return {"error": "Password must be at least 4 characters"}
    return userstore.register_user(username, password)


def handle_login(username: str, password: str, userstore) -> dict:
    if not username or not password:
        return {"error": "Username and password are required"}
    user = userstore.authenticate_user(username, password)
    if not user:
        return {"error": "Invalid username or password"}
    return {"user_id": user["user_id"], "username": user["username"]}


def handle_create_folder(user_id: str, name: str, userstore) -> dict:
    try:
        return {"folder": userstore.create_folder(user_id, name)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_rename_folder(user_id: str, folder_id: str, name: str, userstore) -> dict:
    try:
        return {"folder": userstore.rename_folder(user_id, folder_id, name)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_list_folders(user_id: str, userstore) -> dict:
    return {"folders": userstore.list_folders(user_id)}


def handle_get_folder(user_id: str, folder_id: str, userstore) -> dict:
    try:
        folder = userstore.get_folder(user_id, folder_id)
        if not folder:
            return {"error": "Folder not found"}
        return {"folder": folder, "docs": userstore.get_folder_docs(user_id, folder_id)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_add_documents_to_folder(user_id: str, folder_id: str, doc_ids: list[str], userstore) -> dict:
    try:
        folder = userstore.add_docs_to_folder(user_id, folder_id, doc_ids)
        return {"folder": folder, "docs": userstore.get_folder_docs(user_id, folder_id)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_generate_topics(user_id: str, folder_id: str, ai_client, userstore, vector_store) -> dict:
    try:
        doc_texts = _get_folder_doc_texts(user_id, folder_id, userstore, vector_store)
        if not doc_texts:
            return {"error": "Folder has no retrievable content yet."}
        combined = "\n\n".join(f"[DOC {doc['doc_id']}] {doc['text']}" for doc in doc_texts)[:15000]
        raw = ai_client.invoke(TOPIC_PROMPT_TEMPLATE.format(content=combined), max_tokens=1024)
        try:
            parsed = _parse_json_array(raw)
            topics = [
                {
                    "title": item.get("title", f"Topic {index}"),
                    "summary": item.get("summary", "Study guide topic"),
                    "source_doc_ids": [doc["doc_id"] for doc in doc_texts],
                }
                for index, item in enumerate(parsed[:5], start=1)
            ]
            if not topics:
                raise ValueError("No topics")
        except Exception:
            topics = _fallback_topics(doc_texts, count=5)
        return {"topics": userstore.replace_folder_topics(user_id, folder_id, topics), "raw": raw}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_list_topics(user_id: str, folder_id: str, userstore) -> dict:
    try:
        return {"topics": userstore.list_folder_topics(user_id, folder_id)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_folder_dashboard(user_id: str, folder_id: str, userstore) -> dict:
    try:
        return userstore.get_folder_dashboard(user_id, folder_id)
    except ValueError as exc:
        return {"error": str(exc)}


def handle_create_chat_session(user_id: str, folder_id: str, title: str | None, topic_id: str | None, userstore) -> dict:
    try:
        return {"session": userstore.create_chat_session(user_id, folder_id, title=title, active_topic_id=topic_id)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_list_chat_sessions(user_id: str, folder_id: str, userstore) -> dict:
    try:
        return {"sessions": userstore.list_chat_sessions(user_id, folder_id)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_list_chat_messages(user_id: str, session_id: str, userstore) -> dict:
    try:
        session = userstore.get_chat_session(user_id, session_id)
        if not session:
            return {"error": "Session not found"}
        return {"session": session, "messages": userstore.list_chat_messages(user_id, session_id)}
    except ValueError as exc:
        return {"error": str(exc)}


def handle_chat_message(user_id: str, session_id: str, message: str, topic_id: str | None, ai_client, userstore, vector_store, vector_backend: str, bedrock_kb_id: str) -> dict:
    session = userstore.get_chat_session(user_id, session_id)
    if not session:
        return {"error": "Session not found"}

    user_message = userstore.add_chat_message(user_id, session_id, "user", message, topic_id=topic_id)
    topic = userstore.get_topic(user_id, topic_id) if topic_id else None

    if vector_backend == "bedrock_kb":
        result = ai_client.retrieve_and_generate(query=message, kb_id=bedrock_kb_id)
        answer = result["answer"]
        citations = result["citations"]
    else:
        chunks = vector_store.search(message, top_k=5, filter={"user_id": user_id})
        citations = [
            {"chunk": index + 1, "doc_id": chunk["doc_id"], "score": chunk["score"], "text": chunk["text"][:200]}
            for index, chunk in enumerate(chunks)
        ]
        context = "\n\n".join(f"[chunk {index + 1}] {chunk['text']}" for index, chunk in enumerate(chunks))
        if not context:
            answer = "No relevant content found in your uploaded documents yet."
        else:
            prompt = (
                TOPIC_CHAT_PROMPT_TEMPLATE.format(
                    topic_title=topic["title"],
                    topic_summary=topic["summary"],
                    context=context,
                    question=message,
                )
                if topic
                else PROMPT_TEMPLATE.format(context=context, question=message)
            )
            answer = ai_client.invoke(prompt, max_tokens=512)

    assistant_message = userstore.add_chat_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=answer,
        topic_id=topic_id,
        citations=citations,
    )
    if topic_id and session["folder_id"]:
        userstore.touch_topic_question(user_id, session["folder_id"], topic_id)
    return {"session": userstore.get_chat_session(user_id, session_id), "user_message": user_message, "assistant_message": assistant_message}


def handle_topic_quiz(user_id: str, topic_id: str, question_count: int, ai_client, userstore, vector_store) -> dict:
    topic = userstore.get_topic(user_id, topic_id)
    if not topic:
        return {"error": "Topic not found"}
    docs = userstore.get_topic_source_docs(user_id, topic_id)
    doc_texts = []
    for doc in docs:
        text = _get_doc_text_with_fallback(user_id, doc["doc_id"], vector_store, userstore)
        if text:
            doc_texts.append(text)
    content = f"Topic: {topic['title']}\nSummary: {topic['summary']}\n\n" + "\n\n".join(doc_texts[:3])
    raw = ai_client.invoke(QUIZ_PROMPT_TEMPLATE.format(content=content[:12000], question_count=question_count), max_tokens=2048)
    try:
        quiz = _parse_json_array(raw)
    except Exception:
        quiz = _fallback_quiz(topic["title"], topic["summary"], question_count)
    return {"topic": topic, "quiz": quiz, "raw": raw}


def handle_topic_quiz_submit(user_id: str, topic_id: str, question_count: int, score: int, total: int, userstore, session_id: str | None = None) -> dict:
    topic = userstore.get_topic(user_id, topic_id)
    if not topic:
        return {"error": "Topic not found"}
    attempt = userstore.record_topic_quiz_attempt(
        user_id=user_id,
        folder_id=topic["folder_id"],
        topic_id=topic_id,
        question_count=question_count,
        score=score,
        total=total,
        session_id=session_id,
    )
    return {"attempt": attempt}


def _fallback_summary(text: str) -> str:
    """Generate a simple extractive summary when AI is unavailable."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    selected = [s.strip() for s in sentences[:4] if s.strip()]
    if not selected:
        return "No content available for summary."
    bullets = "\n".join(f"- {sentence}" for sentence in selected[:3])
    takeaway = selected[-1]
    return f"{bullets}\n\nTakeaway: {takeaway}"


def _is_verbose_summary(summary: str) -> bool:
    words = len(re.findall(r"\S+", summary or ""))
    return words > 220 or len(summary or "") > 1400


def _fallback_testable_concepts(text: str) -> list[dict]:
    """Generate keyword-based testable concepts when AI is unavailable."""
    words = [w for w in _tokenize(text) if w not in STOPWORDS]
    common = [w.title() for w, _ in Counter(words).most_common(15)]
    concepts = []
    for i in range(5):
        start = i * 3
        kw = common[start : start + 3] if start + 3 <= len(common) else common[start:] or [f"Concept {i+1}"]
        concepts.append(
            {
                "title": " & ".join(kw),
                "why_testable": f"These terms appear frequently in the document and are likely core exam topics.",
                "key_points": kw,
            }
        )
    return concepts


def _fallback_doc_topics(doc_id: str, text: str) -> list[dict]:
    return _fallback_topics([{"doc_id": doc_id, "text": text}], count=5)


def _format_recent_chat(messages: list[dict], limit: int = 6) -> str:
    recent = messages[-limit:]
    if not recent:
        return "No prior conversation."
    lines = []
    for message in recent:
        role = "User" if message.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {message.get('content', '').strip()}")
    return "\n".join(lines)


def _build_doc_chat_citations(chunks: list[dict]) -> list[dict]:
    citations = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {}) or {}
        chunk_id = metadata.get("chunk_id") or metadata.get("chunk_idx") or f"chunk-{index}"
        citations.append(
            {
                "doc_id": chunk.get("doc_id", ""),
                "chunk_id": str(chunk_id),
                "excerpt": _summarize_text(chunk.get("text", ""), max_chars=320),
            }
        )
    return citations


def _should_refresh_doc_memory(message_count: int, has_memory: bool) -> bool:
    if message_count < 20:
        return False
    if not has_memory:
        return True
    return (message_count - 20) % 6 == 0


def _fallback_memory_summary(messages: list[dict]) -> str:
    if not messages:
        return ""
    recent = messages[-6:]
    snippets = []
    for message in recent:
        role = "User" if message.get("role") == "user" else "Assistant"
        snippets.append(f"{role}: {_summarize_text(message.get('content', ''), max_chars=120)}")
    return " | ".join(snippets)


def _update_doc_chat_memory(user_id: str, doc_id: str, messages: list[dict], session: dict, ai_client, userstore) -> dict | None:
    if not hasattr(userstore, "update_document_chat_session"):
        return session
    if not _should_refresh_doc_memory(len(messages), bool(session.get("memory_summary"))):
        return session
    conversation = _format_recent_chat(messages, limit=min(12, len(messages)))
    try:
        memory_summary = ai_client.invoke(
            DOC_CHAT_MEMORY_PROMPT.format(
                existing_memory=session.get("memory_summary") or "None.",
                conversation=conversation,
            ),
            max_tokens=180,
        ).strip()
    except Exception:
        memory_summary = _fallback_memory_summary(messages)
    updated = userstore.update_document_chat_session(user_id, doc_id, memory_summary=memory_summary, message_count=len(messages))
    return updated or session


def _reformulate_doc_chat_query(question: str, messages: list[dict], ai_client) -> str:
    if not messages:
        return question
    history = _format_recent_chat(messages, limit=6)
    try:
        if hasattr(ai_client, "converse"):
            rewritten = ai_client.converse(
                DOC_CHAT_REWRITE_SYSTEM_PROMPT,
                DOC_CHAT_REWRITE_PROMPT.format(history=history, question=question),
                max_tokens=120,
                temperature=0,
            ).strip()
        else:
            rewritten = ai_client.invoke(
                DOC_CHAT_REWRITE_PROMPT.format(history=history, question=question),
                max_tokens=120,
                temperature=0,
            ).strip()
        return rewritten or question
    except Exception:
        return question


def handle_doc_summary(user_id: str, doc_id: str, ai_client, vector_store, userstore) -> dict:
    document = userstore.get_document(user_id, doc_id) if hasattr(userstore, "get_document") else None
    cached_summary = (document or {}).get("doc_summary")
    if cached_summary and not _is_verbose_summary(cached_summary):
        return {"doc_id": doc_id, "summary": cached_summary, "cached": True}

    text = _get_doc_text_with_fallback(user_id, doc_id, vector_store, userstore)
    if not text.strip():
        return {"error": "No content found for this document. It may still be processing."}
    content = text[:15000]
    try:
        summary = ai_client.invoke(DOC_SUMMARY_PROMPT.format(content=content), max_tokens=384)
    except Exception:
        summary = _fallback_summary(text)
    if hasattr(userstore, "update_document_analysis"):
        userstore.update_document_analysis(user_id, doc_id, summary=summary)
    return {"doc_id": doc_id, "summary": summary, "cached": False}


def handle_doc_testable_concepts(user_id: str, doc_id: str, ai_client, vector_store, userstore) -> dict:
    text = _get_doc_text_with_fallback(user_id, doc_id, vector_store, userstore)
    if not text.strip():
        return {"error": "No content found for this document. It may still be processing."}
    content = text[:15000]
    try:
        raw = ai_client.invoke(DOC_TESTABLE_CONCEPTS_PROMPT.format(content=content), max_tokens=1024)
        concepts = _parse_json_array(raw)
        if not concepts:
            raise ValueError("empty")
    except Exception:
        concepts = _fallback_testable_concepts(text)
    return {"doc_id": doc_id, "concepts": concepts[:5]}


def handle_doc_topics(user_id: str, doc_id: str, ai_client, vector_store, userstore) -> dict:
    document = userstore.get_document(user_id, doc_id) if hasattr(userstore, "get_document") else None
    cached_topics = (document or {}).get("doc_topics") or []
    if cached_topics:
        return {"doc_id": doc_id, "topics": cached_topics, "cached": True}

    text = _get_doc_text(user_id, doc_id, vector_store)
    if not text.strip():
        return {"error": "No content found for this document. It may still be processing."}

    content = text[:15000]
    try:
        raw = ai_client.invoke(DOC_TOPICS_PROMPT.format(content=content), max_tokens=1024)
        parsed = _parse_json_array(raw)
        topics = [
            {
                "title": item.get("title", f"Topic {index}"),
                "summary": item.get("summary", "Study guide topic"),
                "position": index,
                "doc_id": doc_id,
            }
            for index, item in enumerate(parsed[:5], start=1)
        ]
        if not topics:
            raise ValueError("No topics")
    except Exception:
        topics = [
            {**topic, "position": index, "doc_id": doc_id}
            for index, topic in enumerate(_fallback_doc_topics(doc_id, text), start=1)
        ]

    if hasattr(userstore, "update_document_analysis"):
        userstore.update_document_analysis(user_id, doc_id, topics=topics)
    return {"doc_id": doc_id, "topics": topics, "cached": False}


def handle_get_document_chat(user_id: str, doc_id: str, userstore) -> dict:
    document = userstore.get_document(user_id, doc_id) if hasattr(userstore, "get_document") else None
    if not document:
        return {"error": "Document not found"}
    session = userstore.get_or_create_document_chat_session(user_id, doc_id, title=document.get("filename", "Document chat"))
    messages = userstore.list_document_chat_messages(user_id, doc_id)
    if hasattr(userstore, "update_document_chat_session"):
        session = userstore.update_document_chat_session(user_id, doc_id, message_count=len(messages)) or session
    return {"session": session, "messages": messages}


def handle_document_chat_message(user_id: str, doc_id: str, message: str, ai_client, vector_store, userstore) -> dict:
    document = userstore.get_document(user_id, doc_id) if hasattr(userstore, "get_document") else None
    if not document:
        return {"error": "Document not found"}

    session = userstore.get_or_create_document_chat_session(user_id, doc_id, title=document.get("filename", "Document chat"))
    existing_messages = userstore.list_document_chat_messages(user_id, doc_id)
    user_message = userstore.add_document_chat_message(user_id, doc_id, "user", message)

    effective_query = _reformulate_doc_chat_query(message, existing_messages, ai_client)
    chunks = vector_store.search(effective_query, top_k=5, filter={"doc_id": doc_id})
    citations = _build_doc_chat_citations(chunks)
    context = "\n\n".join(f"[chunk {index}] {chunk['text']}" for index, chunk in enumerate(chunks, start=1))

    if not context.strip():
        answer = "I can't answer that from this document because I couldn't find supporting content."
        citations = []
    else:
        try:
            if hasattr(ai_client, "converse"):
                answer = ai_client.converse(
                    DOC_CHAT_SYSTEM_PROMPT,
                    DOC_CHAT_PROMPT.format(
                        memory_summary=session.get("memory_summary") or "None.",
                        context=context,
                        question=message,
                    ),
                    prior_messages=existing_messages[-6:],
                    max_tokens=512,
                    temperature=0.2,
                )
            else:
                answer = ai_client.invoke(
                    DOC_CHAT_PROMPT.format(
                        memory_summary=session.get("memory_summary") or "None.",
                        context=context,
                        question=message,
                    ),
                    max_tokens=512,
                )
        except Exception:
            answer = "AI is currently unavailable. Please try again later."

    assistant_message = userstore.add_document_chat_message(
        user_id,
        doc_id,
        "assistant",
        answer,
        citations=citations,
    )
    all_messages = existing_messages + [user_message, assistant_message]
    updated_session = _update_doc_chat_memory(user_id, doc_id, all_messages, session, ai_client, userstore) or session
    if hasattr(userstore, "update_document_chat_session"):
        updated_session = userstore.update_document_chat_session(user_id, doc_id, message_count=len(all_messages)) or updated_session
    return {
        "session": updated_session,
        "user_message": user_message,
        "assistant_message": assistant_message,
    }
