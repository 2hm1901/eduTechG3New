"""Endpoint handlers. Pure business logic — knows nothing about FastAPI or AWS specifics."""
import io
import uuid
from typing import Optional


PROMPT_TEMPLATE = """You are a study assistant. Answer the student's question using ONLY the
context retrieved from their uploaded lecture notes. Cite the source by chunk
number where possible. If the context does not contain the answer, say so
plainly. Do not invent information.

CONTEXT:
{context}

QUESTION: {question}

ANSWER:"""


def _extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from PDF or .txt upload."""
    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return "(pypdf not installed — install requirements.txt)"
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    # Default: assume UTF-8 text
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def handle_upload(
    user_id: str,
    filename: str,
    data: bytes,
    storage,
    userstore,
    vector_store,
) -> dict:
    """Store the file, extract text, ingest into vector store, record in userstore."""
    doc_id = str(uuid.uuid4())
    key = f"{user_id}/{doc_id}/{filename}"
    location = storage.put(key, data)
    text = _extract_text(filename, data)
    if text.strip():
        vector_store.ingest(doc_id=doc_id, text=text, metadata={"user_id": user_id, "filename": filename})
    userstore.add_doc(
        user_id=user_id,
        doc_id=doc_id,
        metadata={"filename": filename, "size": len(data), "location": location, "chars": len(text)},
    )
    return {
        "doc_id": doc_id,
        "filename": filename,
        "size": len(data),
        "chars_extracted": len(text),
        "location": location,
    }


def handle_query(
    user_id: str,
    question: str,
    ai_client,
    userstore,
    vector_store,
    vector_backend: str,
    bedrock_kb_id: str,
) -> dict:
    """RAG flow: retrieve user's relevant chunks → call AI with context → log + return."""
    if vector_backend == "bedrock_kb":
        # Production path: let Bedrock do retrieve + generate in one call
        result = ai_client.retrieve_and_generate(query=question, kb_id=bedrock_kb_id)
        answer = result["answer"]
        citations = result["citations"]
    else:
        # Local path: do our own retrieve then prompt
        chunks = vector_store.search(question, top_k=5, filter={"user_id": user_id})
        if not chunks:
            answer = "No relevant content found in your uploaded documents. Upload some first."
            citations = []
        else:
            context = "\n\n".join(f"[chunk {i+1}] {c['text']}" for i, c in enumerate(chunks))
            prompt = PROMPT_TEMPLATE.format(context=context, question=question)
            answer = ai_client.invoke(prompt, max_tokens=512)
            citations = [
                {"chunk": i + 1, "doc_id": c["doc_id"], "score": c["score"], "text": c["text"][:200]}
                for i, c in enumerate(chunks)
            ]

    userstore.log_query(user_id=user_id, query=question, answer=answer)
    return {"question": question, "answer": answer, "citations": citations}


def handle_list_docs(user_id: str, userstore) -> dict:
    return {"user_id": user_id, "docs": userstore.list_docs(user_id)}


def handle_recent_queries(user_id: str, userstore, limit: int = 10) -> dict:
    return {"user_id": user_id, "queries": userstore.recent_queries(user_id, limit=limit)}


# ---------------------------------------------------------------------------
# Summary & Quiz — EduTech core features
# ---------------------------------------------------------------------------

SUMMARY_PROMPT_TEMPLATE = """You are a study assistant. Read the following lecture content and produce:
1. A concise ONE-PAGE SUMMARY (max 300 words) of the material.
2. A bullet list of the TOP 5 MOST TESTABLE CONCEPTS — the ideas a student is most likely to be quizzed on.

Format your response exactly as:

## Summary
<your summary here>

## Top 5 Testable Concepts
1. <concept 1> — <one-sentence explanation>
2. <concept 2> — <one-sentence explanation>
3. <concept 3> — <one-sentence explanation>
4. <concept 4> — <one-sentence explanation>
5. <concept 5> — <one-sentence explanation>

LECTURE CONTENT:
{content}
"""

QUIZ_PROMPT_TEMPLATE = """You are a study assistant. Based on the lecture content below, generate exactly 10 multiple-choice quiz questions.

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
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "answer": "A",
    "explanation": "Short explanation why this is correct."
  }}
]

LECTURE CONTENT:
{content}
"""


def _get_doc_text(user_id: str, doc_id: str, vector_store) -> str:
    """Retrieve all stored chunks for a specific document from the vector store."""
    # LocalVector keeps an in-memory list we can iterate directly.
    if hasattr(vector_store, "docs"):
        matched = [text for (_cid, text, md) in vector_store.docs if md.get("doc_id") == doc_id]
        if matched:
            return "\n\n".join(matched)
    # Bedrock KB / other backends: use a broad search filtered by doc_id.
    chunks = vector_store.search("summary overview key concepts", top_k=50, filter={"doc_id": doc_id})
    if chunks:
        return "\n\n".join(c["text"] for c in chunks)
    return ""


def handle_summary(
    user_id: str,
    doc_id: str,
    ai_client,
    vector_store,
) -> dict:
    """Generate a one-page summary + top 5 testable concepts for a document."""
    text = _get_doc_text(user_id, doc_id, vector_store)
    if not text:
        return {"doc_id": doc_id, "summary": "No content found for this document. Upload it again or check the doc_id."}
    # Cap content to avoid token overflow (~12 000 chars ≈ ~3 000 tokens)
    content = text[:12000]
    prompt = SUMMARY_PROMPT_TEMPLATE.format(content=content)
    result = ai_client.invoke(prompt, max_tokens=1024)
    return {"doc_id": doc_id, "summary": result}


def handle_quiz(
    user_id: str,
    doc_id: str,
    ai_client,
    vector_store,
) -> dict:
    """Generate a 10-question multiple-choice quiz from a document."""
    import json as _json

    text = _get_doc_text(user_id, doc_id, vector_store)
    if not text:
        return {"doc_id": doc_id, "quiz": [], "raw": "No content found for this document."}
    content = text[:12000]
    prompt = QUIZ_PROMPT_TEMPLATE.format(content=content)
    raw = ai_client.invoke(prompt, max_tokens=2048)

    # Try to parse the AI response as JSON.
    quiz = []
    try:
        # Strip potential markdown fences the model might add despite instructions.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        quiz = _json.loads(cleaned)
    except Exception:
        pass  # Return raw text so the frontend can still display something.

    return {"doc_id": doc_id, "quiz": quiz, "raw": raw}


def handle_assign_folder(
    user_id: str,
    doc_id: str,
    folder_name: str,
    userstore,
) -> dict:
    """Assign a document to a folder."""
    userstore.update_doc_folder(user_id=user_id, doc_id=doc_id, folder_name=folder_name)
    return {"status": "assigned", "doc_id": doc_id, "folder": folder_name}


def handle_quiz_folder(
    user_id: str,
    folder_name: str,
    ai_client,
    vector_store,
    userstore,
) -> dict:
    """Generate a quiz from all documents in a folder."""
    import json as _json

    docs = userstore.list_docs(user_id)
    folder_docs = [d for d in docs if folder_name in d.get("folders", [])]
    if not folder_docs:
        return {"folder_name": folder_name, "quiz": [], "raw": "No documents found in this folder."}

    texts = []
    for d in folder_docs:
        text = _get_doc_text(user_id, d["doc_id"], vector_store)
        if text:
            texts.append(text)
            
    if not texts:
        return {"folder_name": folder_name, "quiz": [], "raw": "No content found for documents in this folder."}

    content = "\n\n".join(texts)[:12000]
    prompt = QUIZ_PROMPT_TEMPLATE.format(content=content)
    raw = ai_client.invoke(prompt, max_tokens=2048)

    quiz = []
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        quiz = _json.loads(cleaned)
    except Exception:
        pass

    return {"folder_name": folder_name, "quiz": quiz, "raw": raw}


# ---------------------------------------------------------------------------
# Quiz Submit — save results for dashboard tracking
# ---------------------------------------------------------------------------

def handle_quiz_submit(
    user_id: str,
    doc_id: str,
    score: int,
    total: int,
    userstore,
) -> dict:
    """Save a quiz result for the user's learning dashboard."""
    userstore.log_quiz_result(user_id=user_id, doc_id=doc_id, score=score, total=total)
    return {"status": "saved", "user_id": user_id, "doc_id": doc_id, "score": score, "total": total}


# ---------------------------------------------------------------------------
# Learning Dashboard — Task 4
# ---------------------------------------------------------------------------

def handle_dashboard(user_id: str, userstore) -> dict:
    """Return aggregated learning stats for the dashboard."""
    return userstore.get_dashboard_stats(user_id)


# ---------------------------------------------------------------------------
# Authentication — local login/register
# ---------------------------------------------------------------------------

def handle_register(username: str, password: str, userstore) -> dict:
    """Register a new user."""
    if not username or not password:
        return {"error": "Username and password are required"}
    if len(username) < 3:
        return {"error": "Username must be at least 3 characters"}
    if len(password) < 4:
        return {"error": "Password must be at least 4 characters"}
    return userstore.register_user(username, password)


def handle_login(username: str, password: str, userstore) -> dict:
    """Authenticate a user."""
    if not username or not password:
        return {"error": "Username and password are required"}
    user = userstore.authenticate_user(username, password)
    if not user:
        return {"error": "Invalid username or password"}
    return {"user_id": user["user_id"], "username": user["username"]}
