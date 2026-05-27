import { showToast } from "./api.js";
import { bindAuth } from "./auth.js";
import {
  byId,
  getFolderId,
  loadFolderBundle,
  renderFolderChrome,
  renderFolderDocs,
  renderQuizHistory,
  renderTopicProgress,
} from "./folder-common.js";

const folderId = getFolderId();

function renderStats(dashboard) {
  byId("stats-grid").innerHTML = `
    <div class="stat-box"><strong>${dashboard.file_count}</strong><span>Files</span></div>
    <div class="stat-box"><strong>${dashboard.question_count}</strong><span>Questions</span></div>
    <div class="stat-box"><strong>${dashboard.quiz_history.length}</strong><span>Quizzes</span></div>
    <div class="stat-box"><strong>${dashboard.topic_progress.length}</strong><span>Topics</span></div>
  `;
}

async function loadPage() {
  const bundle = await loadFolderBundle(folderId);
  renderFolderChrome(bundle.folder, "dashboard");
  renderStats(bundle.dashboard);
  renderFolderDocs("folder-docs", bundle.docs, "No files.");
  renderTopicProgress("topic-progress", bundle.topics);
  renderQuizHistory("quiz-history", bundle.dashboard.quiz_history);
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
