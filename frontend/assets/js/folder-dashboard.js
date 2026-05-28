import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";

function byId(id) {
  return document.getElementById(id);
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function formatDate(value) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function summarizeText(value = "", maxLength = 220) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (cleaned.length <= maxLength) {
    return cleaned;
  }
  return `${cleaned.slice(0, maxLength - 3).trimEnd()}...`;
}

function flattenTopics(documents) {
  return documents.flatMap((doc) =>
    (doc.topics || []).map((topic) => ({
      ...topic,
      filename: doc.filename,
      source_doc_id: doc.doc_id,
    }))
  );
}

function normalizeTopics(doc) {
  if (Array.isArray(doc.topics)) {
    return doc.topics;
  }
  try {
    return JSON.parse(doc.doc_topics || "[]");
  } catch {
    return [];
  }
}

function normalizeDocuments(documents) {
  return [...documents]
    .map((doc) => {
      const topics = normalizeTopics(doc);
      const hasSummary = Boolean(doc.doc_summary);
      const hasTopics = topics.length > 0;
      let status = "uploaded";
      if (hasSummary && hasTopics) {
        status = "ready";
      } else if (hasSummary) {
        status = "summary_ready";
      } else if (hasTopics) {
        status = "topics_ready";
      }

      return {
        ...doc,
        topics,
        status,
      };
    })
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
}

function buildDashboardFromDocuments(userId, documents) {
  const normalizedDocs = normalizeDocuments(documents);
  const topics = flattenTopics(normalizedDocs);
  const summariesReady = normalizedDocs.filter((doc) => doc.doc_summary).length;
  const pendingAnalysis = normalizedDocs.filter((doc) => !doc.doc_summary && !doc.topics.length).length;

  return {
    user_id: userId,
    total_documents: normalizedDocs.length,
    summaries_ready: summariesReady,
    topics_ready: topics.length,
    pending_analysis: pendingAnalysis,
    documents: normalizedDocs,
    quiz_history: [],
  };
}

async function loadDashboard() {
  try {
    return await api("/api/dashboard");
  } catch {}

  try {
    return await api("/dashboard");
  } catch {}

  const result = await api("/api/bank/documents");
  return buildDashboardFromDocuments(result.user_id || "", result.docs || []);
}

function renderStats(dashboard) {
  byId("stats-grid").innerHTML = `
    <div class="stat-box"><strong>${formatNumber(dashboard.total_documents)}</strong><span>Documents</span></div>
    <div class="stat-box"><strong>${formatNumber(dashboard.summaries_ready)}</strong><span>Summaries Ready</span></div>
    <div class="stat-box"><strong>${formatNumber(dashboard.topics_ready)}</strong><span>Topics Ready</span></div>
    <div class="stat-box"><strong>${formatNumber(dashboard.pending_analysis)}</strong><span>Pending Analysis</span></div>
  `;
}

function renderHeader(dashboard) {
  byId("folder-title").textContent = `${dashboard.user_id || "User"} Dashboard`;
  byId("folder-meta").textContent = `${dashboard.total_documents} documents analyzed`;
  byId("workspace-link").href = "bank.html";
  byId("quiz-link").href = "bank.html";
  byId("dashboard-link").href = "#";
}

function renderDocuments(documents) {
  const host = byId("folder-docs");
  if (!documents.length) {
    host.innerHTML = '<div class="empty">No documents found.</div>';
    return;
  }

  host.innerHTML = documents
    .map(
      (doc) => `
        <article class="simple-list-item">
          <strong>${escapeHtml(doc.filename || doc.doc_id)}</strong>
          <div class="small muted">${escapeHtml(doc.status || "uploaded")}</div>
          <div class="small muted">${formatNumber(doc.size)} bytes | ${formatNumber(doc.chars)} chars</div>
          <div class="small muted">${escapeHtml(formatDate(doc.created_at))}</div>
          <div class="small muted">${escapeHtml(summarizeText(doc.doc_summary || "No summary generated yet.", 140))}</div>
        </article>
      `
    )
    .join("");
}

function renderTopics(documents) {
  const host = byId("topic-progress");
  const topics = flattenTopics(documents);
  if (!topics.length) {
    host.innerHTML = '<div class="empty">No topics generated yet.</div>';
    return;
  }

  host.innerHTML = topics
    .map(
      (topic) => `
        <article class="progress-item">
          <div class="row between">
            <strong>${topic.position || "?"}. ${escapeHtml(topic.title || "Untitled topic")}</strong>
            <span class="chip">${escapeHtml(topic.filename || "")}</span>
          </div>
          <p class="small muted">${escapeHtml(summarizeText(topic.summary || "", 180))}</p>
          <div class="progress-meta">
            <span>Doc ${escapeHtml(topic.source_doc_id || topic.doc_id || "")}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderHistory(documents) {
  const host = byId("quiz-history");
  const readyDocs = documents.filter((doc) => doc.doc_summary || doc.topics.length);
  if (!readyDocs.length) {
    host.innerHTML = '<div class="empty">No document activity yet.</div>';
    return;
  }

  host.innerHTML = readyDocs
    .map(
      (doc) => `
        <article class="history-item">
          <strong>${escapeHtml(doc.filename || doc.doc_id)}</strong>
          <div class="small muted">Upload: ${escapeHtml(formatDate(doc.created_at))}</div>
          <div class="small muted">Summary generated: ${doc.summary_generated_at ? escapeHtml(formatDate(doc.summary_generated_at)) : "Pending"}</div>
          <div class="small muted">Topics generated: ${doc.topics_generated_at ? escapeHtml(formatDate(doc.topics_generated_at)) : "Pending"}</div>
        </article>
      `
    )
    .join("");
}

async function loadPage(userId) {
  const dashboard = await loadDashboard();
  if (!dashboard.user_id) {
    dashboard.user_id = userId;
  }
  dashboard.documents = normalizeDocuments(dashboard.documents || []);
  renderHeader(dashboard);
  renderStats(dashboard);
  renderDocuments(dashboard.documents);
  renderTopics(dashboard.documents);
  renderHistory(dashboard.documents);
}

bindAuth({
  onAuthChange: async (userId) => {
    if (!userId) {
      byId("folder-title").textContent = "Sign in required";
      byId("folder-meta").textContent = "Sign in to continue.";
      return;
    }
    try {
      await loadPage(userId);
    } catch (error) {
      showToast(error.message, "error");
    }
  },
});
