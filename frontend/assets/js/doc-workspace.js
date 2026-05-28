import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";

function byId(id) {
  return document.getElementById(id);
}

function getDocId() {
  const pathMatch = window.location.pathname.match(/\/doc\/([^/]+)/);
  if (pathMatch) return pathMatch[1];
  return new URLSearchParams(window.location.search).get("doc") || "";
}

const docId = getDocId();
const state = {
  doc: null,
  summary: null,
  topics: [],
  session: null,
  chatMessages: [],
  sending: false,
};

function formatContent(text) {
  const safe = escapeHtml(text || "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  const blocks = safe.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean);
  return blocks
    .map((block) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
      const bulletLines = lines.filter((line) => /^[-•]\s+/.test(line));
      if (bulletLines.length === lines.length) {
        return `<ul>${bulletLines.map((line) => `<li>${line.replace(/^[-•]\s+/, "")}</li>`).join("")}</ul>`;
      }
      return `<p>${lines.join("<br>")}</p>`;
    })
    .join("");
}

function renderSummaryPanel() {
  const host = byId("summary-panel");
  if (!state.summary) {
    host.innerHTML = '<div class="empty">Summary not available yet.</div>';
    return;
  }
  host.innerHTML = `<article class="insight-card summary-card"><div class="summary-body">${formatContent(state.summary)}</div></article>`;
}

function renderTopicsPanel() {
  const host = byId("topics-panel");
  if (!state.topics.length) {
    host.innerHTML = '<div class="empty">Topics are still being prepared.</div>';
    return;
  }
  host.innerHTML = state.topics
    .map(
      (topic) => `
        <article class="insight-card topic-card">
          <div class="concept-header">
            <span class="concept-number">${topic.position || ""}</span>
            <strong>${escapeHtml(topic.title || "Untitled topic")}</strong>
          </div>
          <p class="concept-why">${escapeHtml(topic.summary || "")}</p>
        </article>
      `
    )
    .join("");
}

function renderUserBubble(message) {
  return `
    <article class="chat-bubble user">
      <div class="small muted">You</div>
      <div>${formatContent(message.content || "")}</div>
    </article>
  `;
}

function renderCitation(citation) {
  const meta = citation.chunk_id ? escapeHtml(String(citation.chunk_id)) : "Document source";
  return `
    <article class="source-card">
      <div class="source-meta small mono">${meta}</div>
      <p>${escapeHtml(citation.excerpt || "")}</p>
    </article>
  `;
}

function renderAssistantBubble(message) {
  const citations = message.citations || [];
  const sources = citations.length
    ? `
      <details class="sources-toggle">
        <summary>Sources (${citations.length})</summary>
        <div class="sources-list">
          ${citations.map(renderCitation).join("")}
        </div>
      </details>
    `
    : "";
  return `
    <article class="chat-bubble assistant">
      <div class="small muted">StudyBot</div>
      <div>${formatContent(message.content || "")}</div>
      ${sources}
    </article>
  `;
}

function renderChat() {
  const host = byId("chat-messages");
  if (!state.chatMessages.length) {
    host.innerHTML = `
      <div class="empty chat-empty">
        <strong>No questions yet.</strong>
        <p class="muted">Ask about a concept, definition, or section from this document.</p>
      </div>
    `;
    return;
  }

  host.innerHTML = state.chatMessages
    .map((message) => (message.role === "user" ? renderUserBubble(message) : renderAssistantBubble(message)))
    .join("");
  host.scrollTop = host.scrollHeight;
}

async function loadDocMeta() {
  const result = await api("/api/bank/documents");
  const doc = (result.docs || []).find((item) => item.doc_id === docId);
  if (!doc) {
    throw new Error("Document not found");
  }
  state.doc = doc;
  byId("doc-title").textContent = doc.filename;
  byId("doc-meta").textContent = `ID: ${doc.doc_id.slice(0, 8)} • ${Math.round((doc.size || 0) / 1024)} KB`;
  const quizLink = byId("quiz-link");
  if (quizLink) {
    quizLink.href = `/pages/doc-quiz.html?doc=${encodeURIComponent(docId)}`;
  }
}

async function loadSummary() {
  try {
    const result = await api(`/api/documents/${docId}/summary`, { method: "POST" });
    state.summary = result.summary;
  } catch (err) {
    state.summary = `Unable to generate summary: ${err.message}`;
  } finally {
    byId("summary-loading-state").style.display = "none";
    renderSummaryPanel();
  }
}

async function loadTopics() {
  try {
    const result = await api(`/api/documents/${docId}/topics`);
    state.topics = result.topics || [];
  } catch (_err) {
    state.topics = [];
  } finally {
    byId("topics-loading-state").style.display = "none";
    renderTopicsPanel();
  }
}

async function loadChatSession() {
  try {
    const result = await api(`/api/documents/${docId}/chat`);
    state.session = result.session || null;
    state.chatMessages = result.messages || [];
  } catch (err) {
    state.session = null;
    state.chatMessages = [];
    showToast(`Chat unavailable: ${err.message}`, "error");
  } finally {
    byId("chat-loading-state").style.display = "none";
    renderChat();
  }
}

async function loadPage() {
  await loadDocMeta();
  await Promise.all([loadSummary(), loadTopics(), loadChatSession()]);
}

async function sendMessage() {
  if (state.sending) return;
  const input = byId("chat-input");
  const sendBtn = byId("send-btn");
  const message = input.value.trim();
  if (!message) return;

  state.sending = true;
  input.value = "";
  sendBtn.disabled = true;

  const optimistic = {
    message_id: `temp-${Date.now()}`,
    role: "user",
    content: message,
    citations: [],
  };
  state.chatMessages.push(optimistic);
  renderChat();

  try {
    const result = await api(`/api/documents/${docId}/chat/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    state.session = result.session || state.session;
    state.chatMessages[state.chatMessages.length - 1] = result.user_message || optimistic;
    if (result.assistant_message) {
      state.chatMessages.push(result.assistant_message);
    }
    renderChat();
  } catch (err) {
    state.chatMessages[state.chatMessages.length - 1] = {
      ...optimistic,
      content: `${message}\n\nFailed to send: ${err.message}`,
    };
    renderChat();
    showToast(err.message, "error");
  } finally {
    state.sending = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

function bindEvents() {
  byId("send-btn").addEventListener("click", sendMessage);
  byId("chat-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
}

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
      byId("doc-title").textContent = "Error loading document";
      byId("doc-meta").textContent = err.message;
    }
  },
});

bindEvents();
