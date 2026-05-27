import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";
import {
  bindFolderSidebarToggle,
  byId,
  getFolderId,
  getTopicFromQuery,
  loadFolderBundle,
  renderFolderChrome,
  renderQuizHistory,
  renderTopicProgress,
  summarizeText,
} from "./folder-common.js";

const folderId = getFolderId();
const state = {
  folder: null,
  topics: [],
  dashboard: null,
  activeTopicId: getTopicFromQuery(),
  quizQuestions: [],
  quizTopicId: "",
};

function currentTopic() {
  return state.topics.find((topic) => topic.topic_id === state.activeTopicId) || null;
}

function renderTopics() {
  const host = byId("topics-list");
  if (!state.topics.length) {
    host.innerHTML = '<div class="empty">No topics yet.</div>';
    return;
  }

  host.innerHTML = state.topics
    .map(
      (topic) => `
        <button class="topic-item ${topic.topic_id === state.activeTopicId ? "active" : ""}" data-topic="${topic.topic_id}">
          <div class="row between">
            <strong>${topic.position}. ${escapeHtml(topic.title)}</strong>
            <span class="chip">${escapeHtml(topic.status || "new")}</span>
          </div>
          <p class="small muted">${escapeHtml(summarizeText(topic.summary, 180))}</p>
        </button>
      `
    )
    .join("");

  if (!state.activeTopicId && state.topics[0]) {
    state.activeTopicId = state.topics[0].topic_id;
  }
  renderTopicSummary();
}

function renderTopicSummary() {
  const topic = currentTopic();
  if (!topic) {
    byId("quiz-topic-title").textContent = "Pick a topic";
    byId("quiz-topic-summary").textContent = "Select a topic first.";
    return;
  }
  byId("quiz-topic-title").textContent = topic.title;
  byId("quiz-topic-summary").textContent = summarizeText(topic.summary, 260);
}

function renderQuiz(topic, questions) {
  state.quizQuestions = questions;
  state.quizTopicId = topic.topic_id;
  byId("quiz-shell").innerHTML = `
    <div class="quiz-header">
      <span class="chip">${questions.length} questions</span>
    </div>
    ${questions
      .map(
        (question, index) => `
          <article class="quiz-question" data-question="${index}">
            <strong>${index + 1}. ${escapeHtml(question.question)}</strong>
            <div class="stack compact-stack">
              ${Object.entries(question.options || {})
                .map(
                  ([key, value]) => `
                    <label class="answer-option">
                      <input type="radio" name="q-${index}" value="${key}">
                      <span><strong>${key}</strong> ${escapeHtml(value)}</span>
                    </label>
                  `
                )
                .join("")}
            </div>
          </article>
        `
      )
      .join("")}
    <div class="action-stack">
      <button class="btn-primary" id="submit-quiz-btn">Submit quiz</button>
      <div id="quiz-result"></div>
    </div>
  `;
  byId("submit-quiz-btn").addEventListener("click", async () => {
    try {
      await submitQuiz();
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

async function loadPage() {
  const bundle = await loadFolderBundle(folderId);
  state.folder = bundle.folder;
  state.topics = bundle.topics;
  state.dashboard = bundle.dashboard;

  if (state.activeTopicId && !state.topics.some((topic) => topic.topic_id === state.activeTopicId)) {
    state.activeTopicId = "";
  }
  if (!state.activeTopicId && state.topics[0]) {
    state.activeTopicId = state.topics[0].topic_id;
  }

  renderFolderChrome(state.folder, "quiz");
  renderTopics();
  renderQuizHistory("quiz-history", state.dashboard.quiz_history);
  renderTopicProgress("topic-progress", state.topics);
}

async function generateTopics() {
  await api(`/api/folders/${folderId}/topics/generate`, { method: "POST" });
  showToast("Topics ready", "success");
  await loadPage();
}

async function generateQuiz() {
  const topic = currentTopic();
  if (!topic) {
    showToast("Choose a topic first", "error");
    return;
  }

  const count = Number(byId("question-count").value || "10");
  const result = await api(`/api/topics/${topic.topic_id}/quiz`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_count: count }),
  });
  renderQuiz(result.topic, result.quiz || []);
}

async function submitQuiz() {
  const answers = [];
  state.quizQuestions.forEach((question, index) => {
    const choice = document.querySelector(`input[name="q-${index}"]:checked`);
    answers.push(choice?.value || "");
  });

  const score = answers.reduce((sum, answer, index) => sum + (answer === state.quizQuestions[index].answer ? 1 : 0), 0);
  const total = state.quizQuestions.length;
  await api(`/api/topics/${state.quizTopicId}/quiz/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question_count: total,
      score,
      total,
      session_id: null,
    }),
  });
  byId("quiz-result").innerHTML = `<div class="status">Score ${score}/${total} · ${Math.round((score / total) * 100)}%</div>`;
  showToast("Saved", "success");
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

  byId("generate-quiz-btn").addEventListener("click", async () => {
    try {
      await generateQuiz();
    } catch (error) {
      showToast(error.message, "error");
    }
  });

  byId("topics-list").addEventListener("click", (event) => {
    const node = event.target.closest("[data-topic]");
    if (!node) {
      return;
    }
    state.activeTopicId = node.dataset.topic;
    renderTopics();
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
