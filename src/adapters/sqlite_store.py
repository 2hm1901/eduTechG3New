import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.adapters.userstore import _hash_password


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteUserStore:
    """Normalized local store for Bank/Folder/Topic/Chat/Quiz workflows."""

    def __init__(self, db_path: str):
        use_uri = db_path.startswith("file:")
        if db_path != ":memory:" and not use_uri:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, uri=use_uri)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._assert_supported_schema()
        schema_path = Path(__file__).resolve().parents[2] / "migrations" / "001_core_schema.sql"
        self.conn.executescript(schema_path.read_text(encoding="utf-8"))
        self.conn.commit()

    def _table_columns(self, table: str) -> list[str]:
        try:
            rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        except sqlite3.OperationalError:
            return []
        return [row[1] for row in rows]

    def _assert_supported_schema(self) -> None:
        user_columns = self._table_columns("users")
        if user_columns and "user_id" not in user_columns:
            raise ValueError(
                "Legacy SQLite schema detected. Point USERSTORE_SQLITE_PATH to a fresh file such as './_data/studybot.db'."
            )
        if self._table_columns("users_legacy") or self._table_columns("user_docs"):
            raise ValueError(
                "Legacy local DB tables detected. Use a fresh SQLite file for the normalized Bank/Folder schema."
            )

    def _ensure_user(self, user_id: str) -> None:
        row = self.conn.execute(
            "SELECT user_id FROM users WHERE user_id = ? OR username = ?",
            (user_id, user_id),
        ).fetchone()
        if row:
            return
        self.conn.execute(
            "INSERT INTO users (user_id, username, password_hash, salt, display_name, created_at) "
            "VALUES (?, ?, '', '', ?, ?)",
            (user_id, user_id, user_id, _now()),
        )
        self.conn.commit()

    def _require_folder(self, user_id: str, folder_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM folders WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id),
        ).fetchone()
        if not row:
            raise ValueError("Folder not found")
        return row

    def _require_session(self, user_id: str, session_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT s.* FROM chat_sessions s WHERE s.user_id = ? AND s.session_id = ?",
            (user_id, session_id),
        ).fetchone()
        if not row:
            raise ValueError("Session not found")
        return row

    def _row_to_folder(self, row: sqlite3.Row) -> dict:
        return {
            "folder_id": row["folder_id"],
            "name": row["name"],
            "topics_generated": bool(row["topics_generated"]),
            "topics_generated_at": row["topics_generated_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "doc_count": row["doc_count"] or 0,
        }

    def _row_to_topic(self, row: sqlite3.Row) -> dict:
        return {
            "topic_id": row["topic_id"],
            "folder_id": row["folder_id"],
            "title": row["title"],
            "summary": row["summary"],
            "position": row["position"],
            "created_at": row["created_at"],
            "questions_asked": row["questions_asked"] or 0,
            "quizzes_taken": row["quizzes_taken"] or 0,
            "best_score": row["best_score"] or 0,
            "last_studied_at": row["last_studied_at"],
            "status": row["status"] or "new",
        }

    # ---- Auth ----
    def register_user(self, username: str, password: str) -> dict:
        existing = self.conn.execute(
            "SELECT user_id, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        hashed, salt = _hash_password(password)
        now = _now()
        if existing and existing["password_hash"]:
            return {"error": "Username already exists"}
        if existing:
            self.conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, display_name = ? WHERE user_id = ?",
                (hashed, salt, username, existing["user_id"]),
            )
        else:
            self.conn.execute(
                "INSERT INTO users (user_id, username, password_hash, salt, display_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, username, hashed, salt, username, now),
            )
        self.conn.commit()
        return {"user_id": username, "username": username}

    def authenticate_user(self, username: str, password: str):
        row = self.conn.execute(
            "SELECT user_id, username, password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row or not row["password_hash"]:
            return None
        hashed, _ = _hash_password(password, row["salt"])
        if hashed != row["password_hash"]:
            return None
        return {"user_id": row["user_id"], "username": row["username"]}

    # ---- Documents ----
    def add_doc(self, user_id: str, doc_id: str, metadata: dict) -> None:
        self._ensure_user(user_id)
        self.conn.execute(
            "INSERT OR REPLACE INTO documents "
            "(doc_id, user_id, filename, storage_key, mime_type, size_bytes, chars_extracted, extraction_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM documents WHERE doc_id = ?), ?))",
            (
                doc_id,
                user_id,
                metadata.get("filename", doc_id),
                metadata.get("location", ""),
                metadata.get("mime_type"),
                metadata.get("size", 0),
                metadata.get("chars", 0),
                metadata.get("extraction_status", "done"),
                doc_id,
                _now(),
            ),
        )
        self.conn.commit()

    def list_docs(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT d.doc_id, d.filename, d.storage_key, d.mime_type, d.size_bytes, d.chars_extracted,
                   d.extraction_status, d.created_at,
                   GROUP_CONCAT(DISTINCT f.name) AS folder_names,
                   GROUP_CONCAT(DISTINCT f.folder_id) AS folder_ids
            FROM documents d
            LEFT JOIN folder_documents fd ON fd.doc_id = d.doc_id
            LEFT JOIN folders f ON f.folder_id = fd.folder_id AND f.user_id = d.user_id
            WHERE d.user_id = ?
            GROUP BY d.doc_id
            ORDER BY d.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        docs = []
        for row in rows:
            docs.append(
                {
                    "doc_id": row["doc_id"],
                    "filename": row["filename"],
                    "location": row["storage_key"],
                    "mime_type": row["mime_type"],
                    "size": row["size_bytes"],
                    "chars": row["chars_extracted"],
                    "created_at": row["created_at"],
                    "folders": row["folder_names"].split(",") if row["folder_names"] else [],
                    "folder_ids": row["folder_ids"].split(",") if row["folder_ids"] else [],
                }
            )
        return docs

    def get_document(self, user_id: str, doc_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM documents WHERE user_id = ? AND doc_id = ?",
            (user_id, doc_id),
        ).fetchone()
        if not row:
            return None
        return {
            "doc_id": row["doc_id"],
            "user_id": row["user_id"],
            "filename": row["filename"],
            "location": row["storage_key"],
            "mime_type": row["mime_type"],
            "size": row["size_bytes"],
            "chars": row["chars_extracted"],
            "created_at": row["created_at"],
        }

    # ---- Folders ----
    def create_folder(self, user_id: str, name: str) -> dict:
        self._ensure_user(user_id)
        folder_id = str(uuid.uuid4())
        now = _now()
        try:
            self.conn.execute(
                "INSERT INTO folders (folder_id, user_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (folder_id, user_id, name, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Folder name already exists") from exc
        self.conn.commit()
        return self.get_folder(user_id, folder_id)

    def rename_folder(self, user_id: str, folder_id: str, name: str) -> dict:
        self._require_folder(user_id, folder_id)
        try:
            self.conn.execute(
                "UPDATE folders SET name = ?, updated_at = ? WHERE folder_id = ? AND user_id = ?",
                (name, _now(), folder_id, user_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Folder name already exists") from exc
        self.conn.commit()
        return self.get_folder(user_id, folder_id)

    def list_folders(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT f.*, COUNT(fd.doc_id) AS doc_count
            FROM folders f
            LEFT JOIN folder_documents fd ON fd.folder_id = f.folder_id
            WHERE f.user_id = ?
            GROUP BY f.folder_id
            ORDER BY f.updated_at DESC, f.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [self._row_to_folder(row) for row in rows]

    def get_folder(self, user_id: str, folder_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT f.*, COUNT(fd.doc_id) AS doc_count
            FROM folders f
            LEFT JOIN folder_documents fd ON fd.folder_id = f.folder_id
            WHERE f.user_id = ? AND f.folder_id = ?
            GROUP BY f.folder_id
            """,
            (user_id, folder_id),
        ).fetchone()
        return self._row_to_folder(row) if row else None

    def get_folder_by_name(self, user_id: str, name: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT f.*, COUNT(fd.doc_id) AS doc_count
            FROM folders f
            LEFT JOIN folder_documents fd ON fd.folder_id = f.folder_id
            WHERE f.user_id = ? AND f.name = ?
            GROUP BY f.folder_id
            """,
            (user_id, name),
        ).fetchone()
        return self._row_to_folder(row) if row else None

    def add_docs_to_folder(self, user_id: str, folder_id: str, doc_ids: list[str]) -> dict:
        self._require_folder(user_id, folder_id)
        now = _now()
        for doc_id in doc_ids:
            exists = self.conn.execute(
                "SELECT doc_id FROM documents WHERE user_id = ? AND doc_id = ?",
                (user_id, doc_id),
            ).fetchone()
            if not exists:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO folder_documents (folder_id, doc_id, added_at) VALUES (?, ?, ?)",
                (folder_id, doc_id, now),
            )
        self.conn.execute(
            "UPDATE folders SET updated_at = ? WHERE folder_id = ? AND user_id = ?",
            (now, folder_id, user_id),
        )
        self.conn.commit()
        return self.get_folder(user_id, folder_id)

    def get_folder_docs(self, user_id: str, folder_id: str) -> list[dict]:
        self._require_folder(user_id, folder_id)
        rows = self.conn.execute(
            """
            SELECT d.doc_id, d.filename, d.storage_key, d.mime_type, d.size_bytes, d.chars_extracted, d.created_at
            FROM folder_documents fd
            JOIN documents d ON d.doc_id = fd.doc_id
            WHERE fd.folder_id = ? AND d.user_id = ?
            ORDER BY fd.added_at DESC
            """,
            (folder_id, user_id),
        ).fetchall()
        return [
            {
                "doc_id": row["doc_id"],
                "filename": row["filename"],
                "location": row["storage_key"],
                "mime_type": row["mime_type"],
                "size": row["size_bytes"],
                "chars": row["chars_extracted"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ---- Topics ----
    def replace_folder_topics(self, user_id: str, folder_id: str, topics: list[dict]) -> list[dict]:
        self._require_folder(user_id, folder_id)
        now = _now()
        existing = self.conn.execute(
            "SELECT topic_id FROM folder_topics WHERE folder_id = ?",
            (folder_id,),
        ).fetchall()
        for row in existing:
            self.conn.execute("DELETE FROM topic_source_documents WHERE topic_id = ?", (row["topic_id"],))
            self.conn.execute("DELETE FROM topic_progress WHERE topic_id = ?", (row["topic_id"],))
            self.conn.execute("DELETE FROM quiz_attempts WHERE topic_id = ?", (row["topic_id"],))
            self.conn.execute("DELETE FROM chat_messages WHERE topic_id = ?", (row["topic_id"],))
        self.conn.execute("DELETE FROM folder_topics WHERE folder_id = ?", (folder_id,))

        saved = []
        for index, topic in enumerate(topics, start=1):
            topic_id = str(uuid.uuid4())
            self.conn.execute(
                "INSERT INTO folder_topics (topic_id, folder_id, title, summary, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (topic_id, folder_id, topic["title"], topic["summary"], index, now),
            )
            for doc_id in topic.get("source_doc_ids", []):
                self.conn.execute(
                    "INSERT OR IGNORE INTO topic_source_documents (topic_id, doc_id) VALUES (?, ?)",
                    (topic_id, doc_id),
                )
            saved.append(
                {
                    "topic_id": topic_id,
                    "folder_id": folder_id,
                    "title": topic["title"],
                    "summary": topic["summary"],
                    "position": index,
                    "created_at": now,
                    "questions_asked": 0,
                    "quizzes_taken": 0,
                    "best_score": 0,
                    "last_studied_at": None,
                    "status": "new",
                }
            )

        self.conn.execute(
            "UPDATE folders SET topics_generated = 1, topics_generated_at = ?, updated_at = ? WHERE folder_id = ? AND user_id = ?",
            (now, now, folder_id, user_id),
        )
        self.conn.commit()
        return saved

    def list_folder_topics(self, user_id: str, folder_id: str) -> list[dict]:
        self._require_folder(user_id, folder_id)
        rows = self.conn.execute(
            """
            SELECT t.*, p.questions_asked, p.quizzes_taken, p.best_score, p.last_studied_at, p.status
            FROM folder_topics t
            LEFT JOIN topic_progress p ON p.topic_id = t.topic_id AND p.user_id = ?
            WHERE t.folder_id = ?
            ORDER BY t.position ASC
            """,
            (user_id, folder_id),
        ).fetchall()
        return [self._row_to_topic(row) for row in rows]

    def get_topic(self, user_id: str, topic_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT t.*, p.questions_asked, p.quizzes_taken, p.best_score, p.last_studied_at, p.status
            FROM folder_topics t
            JOIN folders f ON f.folder_id = t.folder_id AND f.user_id = ?
            LEFT JOIN topic_progress p ON p.topic_id = t.topic_id AND p.user_id = ?
            WHERE t.topic_id = ?
            """,
            (user_id, user_id, topic_id),
        ).fetchone()
        return self._row_to_topic(row) if row else None

    def get_topic_source_docs(self, user_id: str, topic_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT d.doc_id, d.filename, d.storage_key, d.size_bytes, d.chars_extracted
            FROM topic_source_documents tsd
            JOIN documents d ON d.doc_id = tsd.doc_id
            JOIN folder_topics t ON t.topic_id = tsd.topic_id
            JOIN folders f ON f.folder_id = t.folder_id AND f.user_id = d.user_id
            WHERE tsd.topic_id = ? AND d.user_id = ? AND f.user_id = ?
            """,
            (topic_id, user_id, user_id),
        ).fetchall()
        return [
            {
                "doc_id": row["doc_id"],
                "filename": row["filename"],
                "location": row["storage_key"],
                "size": row["size_bytes"],
                "chars": row["chars_extracted"],
            }
            for row in rows
        ]

    def touch_topic_question(self, user_id: str, folder_id: str, topic_id: str) -> None:
        self._ensure_user(user_id)
        now = _now()
        self.conn.execute(
            """
            INSERT INTO topic_progress (user_id, folder_id, topic_id, questions_asked, quizzes_taken, best_score, last_studied_at, status)
            VALUES (?, ?, ?, 1, 0, 0, ?, 'active')
            ON CONFLICT(user_id, topic_id) DO UPDATE SET
              questions_asked = questions_asked + 1,
              last_studied_at = excluded.last_studied_at,
              status = 'active'
            """,
            (user_id, folder_id, topic_id, now),
        )
        self.conn.commit()

    # ---- Chat ----
    def create_chat_session(self, user_id: str, folder_id: str, title: str | None = None, active_topic_id: str | None = None) -> dict:
        self._ensure_user(user_id)
        self._require_folder(user_id, folder_id)
        session_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            "INSERT INTO chat_sessions (session_id, folder_id, user_id, title, active_topic_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, folder_id, user_id, title, active_topic_id, now, now),
        )
        self.conn.commit()
        return self.get_chat_session(user_id, session_id)

    def get_chat_session(self, user_id: str, session_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT s.*,
                   COUNT(m.message_id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.session_id
            WHERE s.user_id = ? AND s.session_id = ?
            GROUP BY s.session_id
            """,
            (user_id, session_id),
        ).fetchone()
        if not row:
            return None
        return {
            "session_id": row["session_id"],
            "folder_id": row["folder_id"],
            "user_id": row["user_id"],
            "title": row["title"] or "Untitled chat",
            "active_topic_id": row["active_topic_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"] or 0,
        }

    def list_chat_sessions(self, user_id: str, folder_id: str) -> list[dict]:
        self._require_folder(user_id, folder_id)
        rows = self.conn.execute(
            """
            SELECT s.*,
                   COUNT(m.message_id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.session_id
            WHERE s.user_id = ? AND s.folder_id = ?
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            """,
            (user_id, folder_id),
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "folder_id": row["folder_id"],
                "user_id": row["user_id"],
                "title": row["title"] or "Untitled chat",
                "active_topic_id": row["active_topic_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"] or 0,
            }
            for row in rows
        ]

    def add_chat_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        topic_id: str | None = None,
        citations: list[dict] | None = None,
    ) -> dict:
        session = self._require_session(user_id, session_id)
        message_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            "INSERT INTO chat_messages (message_id, session_id, user_id, role, topic_id, content, citations_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, session_id, user_id, role, topic_id, content, json.dumps(citations or []), now),
        )
        title = session["title"]
        if role == "user" and not title:
            title = content[:60]
        self.conn.execute(
            "UPDATE chat_sessions SET updated_at = ?, title = COALESCE(?, title), active_topic_id = COALESCE(?, active_topic_id) "
            "WHERE session_id = ?",
            (now, title, topic_id, session_id),
        )
        self.conn.commit()
        return {
            "message_id": message_id,
            "session_id": session_id,
            "role": role,
            "topic_id": topic_id,
            "content": content,
            "citations": citations or [],
            "created_at": now,
        }

    def list_chat_messages(self, user_id: str, session_id: str) -> list[dict]:
        self._require_session(user_id, session_id)
        rows = self.conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [
            {
                "message_id": row["message_id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "topic_id": row["topic_id"],
                "content": row["content"],
                "citations": json.loads(row["citations_json"] or "[]"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ---- Quizzes ----
    def record_topic_quiz_attempt(
        self,
        user_id: str,
        folder_id: str,
        topic_id: str,
        question_count: int,
        score: int,
        total: int,
        result: dict | None = None,
        session_id: str | None = None,
    ) -> dict:
        self._ensure_user(user_id)
        self._require_folder(user_id, folder_id)
        attempt_id = str(uuid.uuid4())
        now = _now()
        percentage = round(score / total * 100) if total else 0
        self.conn.execute(
            "INSERT INTO quiz_attempts (attempt_id, folder_id, topic_id, user_id, session_id, question_count, score, total, percentage, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (attempt_id, folder_id, topic_id, user_id, session_id, question_count, score, total, percentage, json.dumps(result or {}), now),
        )
        status = "mastered" if percentage >= 80 else "active"
        self.conn.execute(
            """
            INSERT INTO topic_progress (user_id, folder_id, topic_id, questions_asked, quizzes_taken, best_score, last_studied_at, status)
            VALUES (?, ?, ?, 0, 1, ?, ?, ?)
            ON CONFLICT(user_id, topic_id) DO UPDATE SET
              quizzes_taken = quizzes_taken + 1,
              best_score = MAX(best_score, excluded.best_score),
              last_studied_at = excluded.last_studied_at,
              status = excluded.status
            """,
            (user_id, folder_id, topic_id, percentage, now, status),
        )
        self.conn.commit()
        return {
            "attempt_id": attempt_id,
            "folder_id": folder_id,
            "topic_id": topic_id,
            "score": score,
            "total": total,
            "percentage": percentage,
            "created_at": now,
        }

    def list_folder_quiz_attempts(self, user_id: str, folder_id: str, limit: int = 20) -> list[dict]:
        self._require_folder(user_id, folder_id)
        rows = self.conn.execute(
            """
            SELECT q.*, t.title AS topic_title
            FROM quiz_attempts q
            JOIN folder_topics t ON t.topic_id = q.topic_id
            WHERE q.user_id = ? AND q.folder_id = ?
            ORDER BY q.created_at DESC
            LIMIT ?
            """,
            (user_id, folder_id, limit),
        ).fetchall()
        return [
            {
                "attempt_id": row["attempt_id"],
                "topic_id": row["topic_id"],
                "topic_title": row["topic_title"],
                "question_count": row["question_count"],
                "score": row["score"],
                "total": row["total"],
                "percentage": row["percentage"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ---- Folder dashboard ----
    def get_folder_dashboard(self, user_id: str, folder_id: str) -> dict:
        folder = self.get_folder(user_id, folder_id)
        if not folder:
            raise ValueError("Folder not found")
        question_count = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM chat_messages m
            JOIN chat_sessions s ON s.session_id = m.session_id
            WHERE s.user_id = ? AND s.folder_id = ? AND m.role = 'user'
            """,
            (user_id, folder_id),
        ).fetchone()[0]
        quiz_history = self.list_folder_quiz_attempts(user_id, folder_id, limit=10)
        topics = self.list_folder_topics(user_id, folder_id)
        return {
            "folder": folder,
            "file_count": folder["doc_count"],
            "question_count": question_count,
            "quiz_history": quiz_history,
            "topic_progress": topics,
        }
