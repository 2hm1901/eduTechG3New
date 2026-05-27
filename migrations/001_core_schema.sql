PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL DEFAULT '',
  salt TEXT NOT NULL DEFAULT '',
  display_name TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  storage_key TEXT NOT NULL,
  mime_type TEXT,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  chars_extracted INTEGER NOT NULL DEFAULT 0,
  extraction_status TEXT NOT NULL DEFAULT 'done',
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_user_created
ON documents(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS folders (
  folder_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  topics_generated INTEGER NOT NULL DEFAULT 0,
  topics_generated_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id, name),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS folder_documents (
  folder_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY (folder_id, doc_id),
  FOREIGN KEY (folder_id) REFERENCES folders(folder_id),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

CREATE INDEX IF NOT EXISTS idx_folder_documents_doc
ON folder_documents(doc_id);

CREATE TABLE IF NOT EXISTS folder_topics (
  topic_id TEXT PRIMARY KEY,
  folder_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  position INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(folder_id, position),
  FOREIGN KEY (folder_id) REFERENCES folders(folder_id)
);

CREATE TABLE IF NOT EXISTS topic_source_documents (
  topic_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  PRIMARY KEY (topic_id, doc_id),
  FOREIGN KEY (topic_id) REFERENCES folder_topics(topic_id),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
  session_id TEXT PRIMARY KEY,
  folder_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  title TEXT,
  active_topic_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (folder_id) REFERENCES folders(folder_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (active_topic_id) REFERENCES folder_topics(topic_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_folder_updated
ON chat_sessions(folder_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  message_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  topic_id TEXT,
  content TEXT NOT NULL,
  citations_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (topic_id) REFERENCES folder_topics(topic_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
ON chat_messages(session_id, created_at ASC);

CREATE TABLE IF NOT EXISTS quiz_attempts (
  attempt_id TEXT PRIMARY KEY,
  folder_id TEXT NOT NULL,
  topic_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  session_id TEXT,
  question_count INTEGER NOT NULL,
  score INTEGER NOT NULL,
  total INTEGER NOT NULL,
  percentage INTEGER NOT NULL,
  result_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (folder_id) REFERENCES folders(folder_id),
  FOREIGN KEY (topic_id) REFERENCES folder_topics(topic_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_quiz_attempts_folder_created
ON quiz_attempts(folder_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_quiz_attempts_topic_created
ON quiz_attempts(topic_id, created_at DESC);

CREATE TABLE IF NOT EXISTS topic_progress (
  user_id TEXT NOT NULL,
  folder_id TEXT NOT NULL,
  topic_id TEXT NOT NULL,
  questions_asked INTEGER NOT NULL DEFAULT 0,
  quizzes_taken INTEGER NOT NULL DEFAULT 0,
  best_score INTEGER NOT NULL DEFAULT 0,
  last_studied_at TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  PRIMARY KEY (user_id, topic_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (folder_id) REFERENCES folders(folder_id),
  FOREIGN KEY (topic_id) REFERENCES folder_topics(topic_id)
);
