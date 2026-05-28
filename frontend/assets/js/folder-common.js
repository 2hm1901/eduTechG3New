import { api, escapeHtml } from "./api.js";

const SIDEBAR_KEY = "sb_folder_sidebar_collapsed";

export function byId(id) {
  return document.getElementById(id);
}

export function getFolderId() {
  const queryFolder = new URLSearchParams(window.location.search).get("folder");
  if (queryFolder) {
    return queryFolder;
  }
  const parts = window.location.pathname.split("/").filter(Boolean);
  const folderIndex = parts.indexOf("folder");
  return folderIndex >= 0 ? parts[folderIndex + 1] || "" : "";
}

export function getTopicFromQuery() {
  return new URLSearchParams(window.location.search).get("topic") || "";
}

export function summarizeText(value = "", maxLength = 180) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (cleaned.length <= maxLength) {
    return cleaned;
  }
  return `${cleaned.slice(0, maxLength - 1).trimEnd()}…`;
}

export function bindFolderSidebarToggle() {
  const sidebar = byId("folder-sidebar");
  const toggle = byId("sidebar-toggle");
  const icon = byId("sidebar-toggle-icon");
  if (!sidebar || !toggle || !icon) {
    return;
  }

  const apply = (collapsed) => {
    document.body.classList.toggle("left-sidebar-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "Expand left sidebar" : "Collapse left sidebar");
    icon.textContent = collapsed ? "›" : "‹";
  };

  let collapsed = window.localStorage.getItem(SIDEBAR_KEY) === "1";
  apply(collapsed);

  toggle.addEventListener("click", () => {
    collapsed = !collapsed;
    window.localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    apply(collapsed);
  });
}

export async function loadFolderBundle(folderId) {
  const [folderResult, topicsResult, sessionsResult, dashboard] = await Promise.all([
    api(`/api/folders/${folderId}`),
    api(`/api/folders/${folderId}/topics`),
    api(`/api/folders/${folderId}/sessions`),
    api(`/api/folders/${folderId}/dashboard`),
  ]);

  return {
    folder: folderResult.folder,
    docs: folderResult.docs || [],
    topics: topicsResult.topics || [],
    sessions: sessionsResult.sessions || [],
    dashboard,
  };
}

export function renderFolderChrome(folder, activeView) {
  byId("folder-title").textContent = folder.name;
  byId("folder-meta").textContent = `${folder.doc_count} files · ${folder.topics_generated ? "topics ready" : "no topics"}`;

  const workspaceHref = `/pages/folder-workspace.html?folder=${folder.folder_id}`;
  const quizHref = `/pages/folder-quiz.html?folder=${folder.folder_id}`;
  const dashboardHref = `/pages/folder-dashboard.html?folder=${folder.folder_id}`;

  byId("workspace-link").href = workspaceHref;
  byId("quiz-link").href = quizHref;
  byId("dashboard-link").href = dashboardHref;

  const quizCta = byId("quiz-cta");
  if (quizCta) {
    quizCta.href = quizHref;
  }
  const dashboardCta = byId("dashboard-cta");
  if (dashboardCta) {
    dashboardCta.href = dashboardHref;
  }

  const navMap = {
    workspace: "workspace-link",
    quiz: "quiz-link",
    dashboard: "dashboard-link",
  };

  Object.values(navMap).forEach((id) => byId(id)?.classList.remove("active"));
  byId(navMap[activeView])?.classList.add("active");
}

export function renderFolderDocs(hostId, docs, emptyMessage) {
  const host = byId(hostId);
  if (!docs.length) {
    host.innerHTML = `<div class="empty">${escapeHtml(emptyMessage)}</div>`;
    return;
  }

  host.innerHTML = docs
    .map(
      (doc) => `
        <div class="simple-list-item">
          <strong>${escapeHtml(doc.filename)}</strong>
        </div>
      `
    )
    .join("");
}

export function renderTopicProgress(hostId, topics) {
  const host = byId(hostId);
  if (!topics.length) {
    host.innerHTML = '<div class="empty">No topics yet.</div>';
    return;
  }

  host.innerHTML = topics
    .map(
      (topic) => `
        <article class="progress-item">
          <div class="row between">
            <strong>${topic.position}. ${escapeHtml(topic.title)}</strong>
            <span class="chip">${escapeHtml(topic.status || "new")}</span>
          </div>
          <p class="small muted">${escapeHtml(summarizeText(topic.summary, 180))}</p>
          <div class="progress-meta">
            <span>${topic.questions_asked || 0} questions</span>
            <span>${topic.quizzes_taken || 0} quizzes</span>
            <span>Best ${topic.best_score || 0}%</span>
          </div>
        </article>
      `
    )
    .join("");
}

export function renderQuizHistory(hostId, attempts) {
  const host = byId(hostId);
  if (!attempts.length) {
    host.innerHTML = '<div class="empty">No attempts yet.</div>';
    return;
  }

  host.innerHTML = attempts
    .map(
      (quiz) => `
        <article class="history-item">
          <strong>${escapeHtml(quiz.topic_title)}</strong>
          <div class="small muted">${quiz.score}/${quiz.total} · ${quiz.percentage}%</div>
        </article>
      `
    )
    .join("");
}
