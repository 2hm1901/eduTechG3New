import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";

function byId(id) {
  return document.getElementById(id);
}

function getDocId() {
  // Support clean URL: /doc/{doc_id}
  const pathMatch = window.location.pathname.match(/\/doc\/([^/]+)/);
  if (pathMatch) return pathMatch[1];
  // Fallback to query parameter
  return new URLSearchParams(window.location.search).get("doc") || "";
}

const docId = getDocId();
const state = {
  doc: null,
  summary: null,
  topics: [],
  chatMessages: [],
};

/* ──────────── rendering ──────────── */

function renderSummaryBubble(summary) {
  return `
    <article class="chat-bubble assistant summary-bubble">
      <div class="bubble-header">
        <span class="bubble-icon">📝</span>
        <strong class="bubble-label">One-Page Summary</strong>
      </div>
      <div class="bubble-body summary-body">${formatContent(summary)}</div>
    </article>
  `;
}

function renderTopicsBubble(topics) {
  if (!topics?.length) {
    return `
      <article class="chat-bubble assistant concepts-bubble">
        <div class="bubble-header">
          <span class="bubble-icon">📚</span>
          <strong class="bubble-label">Five Study Topics</strong>
        </div>
        <div class="bubble-body"><p class="muted">Topics are being generated...</p></div>
      </article>
    `;
  }
  const topicCards = topics
    .map(
      (topic) => `
        <div class="concept-card">
          <div class="concept-header">
            <span class="concept-number">${topic.position || ""}</span>
            <strong>${escapeHtml(topic.title || "Untitled topic")}</strong>
          </div>
          <p class="concept-why">${escapeHtml(topic.summary || "")}</p>
        </div>
      `
    )
    .join("");
  return `
    <article class="chat-bubble assistant concepts-bubble">
      <div class="bubble-header">
        <span class="bubble-icon">📚</span>
        <strong class="bubble-label">Five Study Topics</strong>
      </div>
      <div class="bubble-body concepts-grid">${topicCards}</div>
    </article>
  `;
}

function renderUserBubble(message) {
  return `
    <article class="chat-bubble user">
      <div class="small muted">You</div>
      <div>${escapeHtml(message)}</div>
    </article>
  `;
}

function renderAssistantBubble(answer, citations) {
  const citationsHtml =
    citations?.length
      ? `<div class="chat-citations">${citations
          .map(
            (c) =>
              `<span class="chip small mono">${escapeHtml((c.doc_id || "").slice(0, 8))} · ${escapeHtml(String(c.score || ""))}</span>`
          )
          .join("")}</div>`
      : "";
  return `
    <article class="chat-bubble assistant">
      <div class="small muted">StudyBot</div>
      <div>${formatContent(answer)}</div>
      ${citationsHtml}
    </article>
  `;
}

function formatContent(text) {
  // Basic markdown-like formatting: preserve paragraphs and line breaks
  return escapeHtml(text)
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/- /g, "• ");
}

function renderChat() {
  const host = byId("chat-messages");
  let html = "";

  if (state.summary) {
    html += renderSummaryBubble(state.summary);
  }
  html += renderTopicsBubble(state.topics);

  for (const msg of state.chatMessages) {
    if (msg.role === "user") {
      html += renderUserBubble(msg.content);
    } else {
      html += renderAssistantBubble(msg.content, msg.citations);
    }
  }

  if (!html) {
    html = '<div class="empty">No content yet.</div>';
  }

  host.innerHTML = html;
  host.scrollTop = host.scrollHeight;
}

/* ──────────── loading ──────────── */

async function loadDocMeta() {
  const result = await api("/api/bank/documents");
  const doc = (result.docs || []).find((d) => d.doc_id === docId);
  if (!doc) {
    throw new Error("Document not found");
  }
  state.doc = doc;
  byId("doc-title").textContent = doc.filename;
  byId("doc-meta").textContent = `Document ID: ${doc.doc_id.slice(0, 8)}`;
}

async function loadSummary() {
  try {
    const result = await api(`/api/documents/${docId}/summary`, { method: "POST" });
    state.summary = result.summary;
  } catch (err) {
    state.summary = "Unable to generate summary: " + err.message;
  }
}

async function loadTopics() {
  try {
    const result = await api(`/api/documents/${docId}/topics`);
    state.topics = result.topics || [];
  } catch (_err) {
    state.topics = [];
  }
}

async function loadPage() {
  // Show loading state
  byId("loading-state").style.display = "grid";

  try {
    await loadDocMeta();

    // Load summary first, render it, then load document topics.
    await loadSummary();
    byId("loading-state").style.display = "none";
    renderChat();

    await loadTopics();
    renderChat();
  } catch (err) {
    byId("loading-state").style.display = "none";
    showToast(err.message, "error");
    byId("doc-title").textContent = "Error loading document";
    byId("doc-meta").textContent = err.message;
  }
}

/* ──────────── chat ──────────── */

async function sendMessage() {
  const input = byId("chat-input");
  const message = input.value.trim();
  if (!message) return;

  state.chatMessages.push({ role: "user", content: message });
  input.value = "";
  renderChat();

  try {
    const result = await api(`/api/documents/${docId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    state.chatMessages.push({
      role: "assistant",
      content: result.answer,
      citations: result.citations,
    });
    renderChat();
  } catch (err) {
    state.chatMessages.push({
      role: "assistant",
      content: "Error: " + err.message,
    });
    renderChat();
    showToast(err.message, "error");
  }
}

/* ──────────── events ──────────── */

function bindEvents() {
  byId("send-btn").addEventListener("click", sendMessage);
  byId("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });
}

/* ──────────── init ──────────── */

bindAuth({
  onAuthChange: async (userId) => {
    if (!userId) {
      byId("doc-title").textContent = "Sign in required";
      byId("doc-meta").textContent = "Sign in to continue.";
      return;
    }
    try {
      await loadPage();
    } catch (err) {
      showToast(err.message, "error");
    }
  },
});

bindEvents();
