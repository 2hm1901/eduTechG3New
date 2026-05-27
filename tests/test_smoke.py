"""End-to-end smoke tests for the Bank -> Folder workspace flow."""
import os
import sys
from pathlib import Path

os.environ.setdefault("AI_BACKEND", "local")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("USERSTORE_BACKEND", "sqlite")
os.environ.setdefault("VECTOR_BACKEND", "local")

_project_root = Path(__file__).resolve().parent.parent
os.environ["STORAGE_LOCAL_DIR"] = str(_project_root / "_data" / "uploads")
os.environ["USERSTORE_SQLITE_PATH"] = ":memory:"
sys.path.insert(0, str(_project_root))

from fastapi.testclient import TestClient
from src.app import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_bank_lists_docs_per_user_isolation():
    client.post(
        "/api/bank/documents/upload",
        files={"file": ("alice.txt", b"alice doc", "text/plain")},
        headers={"X-User-Id": "user-A"},
    )
    client.post(
        "/api/bank/documents/upload",
        files={"file": ("bob.txt", b"bob doc", "text/plain")},
        headers={"X-User-Id": "user-B"},
    )

    a_docs = client.get("/api/bank/documents", headers={"X-User-Id": "user-A"}).json()["docs"]
    b_docs = client.get("/api/bank/documents", headers={"X-User-Id": "user-B"}).json()["docs"]

    assert any(doc["filename"] == "alice.txt" for doc in a_docs)
    assert all(doc["filename"] != "bob.txt" for doc in a_docs)
    assert any(doc["filename"] == "bob.txt" for doc in b_docs)


def test_folder_topic_session_and_quiz_flow():
    upload = client.post(
        "/api/bank/documents/upload",
        files={"file": ("folder.txt", b"Machine learning models use gradient descent and validation metrics.", "text/plain")},
        headers={"X-User-Id": "workspace-user"},
    )
    assert upload.status_code == 200, upload.text
    doc_id = upload.json()["doc_id"]

    folder = client.post(
        "/api/folders",
        json={"name": "ML Revision"},
        headers={"X-User-Id": "workspace-user"},
    )
    assert folder.status_code == 200, folder.text
    folder_id = folder.json()["folder"]["folder_id"]

    attach = client.post(
        f"/api/folders/{folder_id}/documents",
        json={"doc_ids": [doc_id]},
        headers={"X-User-Id": "workspace-user"},
    )
    assert attach.status_code == 200, attach.text
    assert len(attach.json()["docs"]) == 1

    topics = client.post(
        f"/api/folders/{folder_id}/topics/generate",
        headers={"X-User-Id": "workspace-user"},
    )
    assert topics.status_code == 200, topics.text
    assert len(topics.json()["topics"]) == 5
    topic_id = topics.json()["topics"][0]["topic_id"]

    session = client.post(
        f"/api/folders/{folder_id}/sessions",
        json={"title": "Session 1", "topic_id": topic_id},
        headers={"X-User-Id": "workspace-user"},
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["session"]["session_id"]

    message = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"message": "What should I revise first?", "topic_id": topic_id},
        headers={"X-User-Id": "workspace-user"},
    )
    assert message.status_code == 200, message.text
    assert "assistant_message" in message.json()

    messages = client.get(
        f"/api/sessions/{session_id}/messages",
        headers={"X-User-Id": "workspace-user"},
    )
    assert messages.status_code == 200
    assert len(messages.json()["messages"]) == 2

    quiz = client.post(
        f"/api/topics/{topic_id}/quiz",
        json={"question_count": 4},
        headers={"X-User-Id": "workspace-user"},
    )
    assert quiz.status_code == 200, quiz.text
    assert len(quiz.json()["quiz"]) == 4

    submit = client.post(
        f"/api/topics/{topic_id}/quiz/submit",
        json={"question_count": 4, "score": 3, "total": 4, "session_id": session_id},
        headers={"X-User-Id": "workspace-user"},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["attempt"]["percentage"] == 75

    dashboard = client.get(
        f"/api/folders/{folder_id}/dashboard",
        headers={"X-User-Id": "workspace-user"},
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["question_count"] == 1
    assert len(dashboard.json()["quiz_history"]) == 1
