import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";
import {
  bindFolderSidebarToggle,
  byId,
  getFolderId,
  loadFolderBundle,
  renderFolderChrome,
  renderFolderDocs,
  summarizeText,
} from "./folder-common.js";

const folderId = getFolderId();
const state = {
  folder: null,
  docs: [],
  topics: [],
  sessions: [],
  dashboard: null,
  activeSessionId: "",
  activeTopicId: "",
};

function currentTopic() {
  return state.topics.find((topic) => topic.topic_id === state.activeTopicId) || null;
}

function renderFocusTopic() {
  const topic = currentTopic();
  if (!topic) {
    byId("focus-topic-card").innerHTML = `
      <strong>All documents</strong>
      <span class="muted small">No topic selected</span>
    `;
    return;
  }

  byId("focus-topic-card").innerHTML = `
    <strong>${escapeHtml(topic.title)}</strong>
    <span class="muted small">${escapeHtml(summarizeText(topic.summary, 150))}</span>
  `;
}

function renderSessions() {
  const host = byId("sessions-list");
  if (!state.sessions.length) {
    host.innerHTML = '<div class="empty">No sessions yet.</div>';
    return;
  }

  host.innerHTML = state.sessions
    .map(
      (session) => `
        <button class="session-item ${session.session_id === state.activeSessionId ? "active" : ""}" data-session="${session.session_id}">
          <strong>${escapeHtml(session.title)}</strong>
          <span class="small muted">${session.message_count} messages</span>
        </button>
      `
    )
    .join("");
}

function renderTopics() {
  const host = byId("topics-list");
  if (!state.topics.length) {
    host.innerHTML = '<div class="empty">No topics yet.</div>';
    byId("topic-select").innerHTML = '<option value="">All documents</option>';
    renderFocusTopic();
    return;
  }

  host.innerHTML = state.topics
    .map(
      (topic) => `
        <article class="topic-item ${topic.topic_id === state.activeTopicId ? "active" : ""}">
          <div class="row between">
            <strong>${topic.position}. ${escapeHtml(topic.title)}</strong>
            <span class="chip">${escapeHtml(topic.status || "new")}</span>
          </div>
          <p class="small muted">${escapeHtml(summarizeText(topic.summary, 180))}</p>
          <div class="topic-actions">
            <button class="btn-secondary" data-action="focus-topic" data-topic="${topic.topic_id}">Focus</button>
            <a class="btn btn-secondary" href="/folder/${folderId}/quiz?topic=${topic.topic_id}">Quiz</a>
          </div>
        </article>
      `
    )
    .join("");

  byId("topic-select").innerHTML =
    '<option value="">All documents</option>' +
    state.topics.map((topic) => `<option value="${topic.topic_id}">${escapeHtml(topic.title)}</option>`).join("");
  byId("topic-select").value = state.activeTopicId;
  renderFocusTopic();
}

function renderWorkspaceSignals() {
  const dashboard = state.dashboard;
  byId("workspace-signals").innerHTML = `
    <div class="metric-pill">
      <strong>${state.docs.length}</strong>
      <span>Files</span>
    </div>
    <div class="metric-pill">
      <strong>${state.sessions.length}</strong>
      <span>Sessions</span>
    </div>
    <div class="metric-pill">
      <strong>${dashboard.question_count}</strong>
      <span>Questions</span>
    </div>
    <div class="metric-pill">
      <strong>${dashboard.quiz_history.length}</strong>
      <span>Quizzes</span>
    </div>
  `;
}

async function loadMessages(sessionId) {
  const result = await api(`/api/sessions/${sessionId}/messages`);
  byId("chat-messages").innerHTML = result.messages.length
    ? result.messages
        .map(
          (message) => `
            <article class="chat-bubble ${message.role === "user" ? "user" : "assistant"}">
              <div class="small muted">${message.role === "user" ? "You" : "StudyBot"}</div>
              <div>${escapeHtml(message.content)}</div>
              ${
                message.citations?.length
                  ? `<div class="chat-citations">${message.citations
                      .map((citation) => `<span class="chip small mono">${escapeHtml((citation.doc_id || "").slice(0, 8))} · ${escapeHtml(String(citation.score || ""))}</span>`)
                      .join("")}</div>`
                  : ""
              }
            </article>
          `
        )
        .join("")
    : '<div class="empty">No messages yet.</div>';
  byId("chat-messages").scrollTop = byId("chat-messages").scrollHeight;
}

async function loadPage() {
  const bundle = await loadFolderBundle(folderId);
  state.folder = bundle.folder;
  state.docs = bundle.docs;
  state.topics = bundle.topics;
  state.sessions = bundle.sessions;
  state.dashboard = bundle.dashboard;

  if (state.activeSessionId && !state.sessions.some((session) => session.session_id === state.activeSessionId)) {
    state.activeSessionId = "";
  }
  if (state.activeTopicId && !state.topics.some((topic) => topic.topic_id === state.activeTopicId)) {
    state.activeTopicId = "";
  }
  if (!state.activeSessionId && state.sessions[0]) {
    state.activeSessionId = state.sessions[0].session_id;
  }

  renderFolderChrome(state.folder, "workspace");
  renderFolderDocs("folder-docs", state.docs, "No files.");
  renderSessions();
  renderTopics();
  renderWorkspaceSignals();

  if (state.activeSessionId) {
    await loadMessages(state.activeSessionId);
  } else {
    byId("chat-messages").innerHTML = '<div class="empty">Start a session.</div>';
  }
}

async function createSession(topicId = null) {
  const shortTitle = topicId ? "Topic chat" : "Chat";
  const result = await api(`/api/folders/${folderId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: shortTitle, topic_id: topicId }),
  });
  state.activeSessionId = result.session.session_id;
  await loadPage();
}

async function sendMessage() {
  const input = byId("chat-input");
  const message = input.value.trim();
  if (!message) {
    return;
  }

  if (!state.activeSessionId) {
    await createSession(state.activeTopicId || null);
  }

  await api(`/api/sessions/${state.activeSessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, topic_id: state.activeTopicId || null }),
  });
  input.value = "";
  await loadPage();
}

async function generateTopics() {
  await api(`/api/folders/${folderId}/topics/generate`, { method: "POST" });
  showToast("Topics ready", "success");
  await loadPage();
}

function bindEvents() {
  byId("generate-topics-btn").addEventListener("click", async () => {
    try {
      await generateTopics();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  byId("new-session-btn").addEventListener("click", async () => {
    try {
      await createSession(state.activeTopicId || null);
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  byId("send-btn").addEventListener("click", async () => {
    try {
      await sendMessage();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  byId("chat-input").addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      try {
        await sendMessage();
      } catch (error) {
        showToast(error.message, "error");
      }
    }
  });

  byId("topic-select").addEventListener("change", (event) => {
    state.activeTopicId = event.target.value;
    renderTopics();
  });

  byId("sessions-list").addEventListener("click", async (event) => {
    const node = event.target.closest("[data-session]");
    if (!node) {
      return;
    }
    state.activeSessionId = node.dataset.session;
    renderSessions();
    try {
      await loadMessages(state.activeSessionId);
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  byId("topics-list").addEventListener("click", async (event) => {
    const node = event.target.closest("[data-action='focus-topic']");
    if (!node) {
      return;
    }
    state.activeTopicId = node.dataset.topic;
    renderTopics();
    renderFocusTopic();
    if (!state.activeSessionId) {
      try {
        await createSession(state.activeTopicId);
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      showToast("Topic selected", "success");
    }
  });
}

bindAuth({
  onAuthChange: async (userId) => {
    if (!userId) {
      byId("folder-title").textContent = "Sign in required";
      byId("folder-meta").textContent = "Sign in to continue.";
      return;
    }
    try {
      await loadPage();
    } catch (error) {
      showToast(error.message, "error");
    }
  },
});

bindFolderSidebarToggle();
bindEvents();
