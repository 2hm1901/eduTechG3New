import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";

function byId(id) {
  return document.getElementById(id);
}

function getDocId() {
  return new URLSearchParams(window.location.search).get("doc") || "";
}

const docId = getDocId();
const state = {
  doc: null,
  quizQuestions: [],
};

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

async function loadQuiz() {
  try {
    const result = await api(`/quiz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId }),
    });
    
    state.quizQuestions = result.quiz || [];
    renderQuiz();
  } catch (err) {
    throw new Error("Unable to generate quiz: " + err.message);
  }
}

function renderQuiz() {
  const host = byId("quiz-questions");
  if (!state.quizQuestions.length) {
    host.innerHTML = '<div class="empty">No questions generated.</div>';
    return;
  }

  host.innerHTML = state.quizQuestions
    .map(
      (question, index) => `
        <article class="quiz-question" data-question="${index}" style="margin-bottom: 2rem;">
          <strong style="display: block; margin-bottom: 1rem; font-size: 1.1rem;">${index + 1}. ${escapeHtml(question.question)}</strong>
          <div class="stack compact-stack">
            ${Object.entries(question.options || {})
              .map(
                ([key, value]) => `
                  <label class="answer-option" style="cursor: pointer; align-items: center; padding: 12px 16px;">
                    <input type="radio" name="q-${index}" value="${key}" style="width: auto; margin: 0; transform: scale(1.2);">
                    <span style="flex: 1; line-height: 1.4;"><strong>${key})</strong> ${escapeHtml(value)}</span>
                  </label>
                `
              )
              .join("")}
          </div>
        </article>
      `
    )
    .join("");
    
  byId("loading-state").style.display = "none";
  byId("quiz-container").style.display = "block";
}

function submitQuiz() {
  const answers = [];
  let isComplete = true;
  
  state.quizQuestions.forEach((question, index) => {
    const choice = document.querySelector(`input[name="q-${index}"]:checked`);
    if (!choice) {
      isComplete = false;
    }
    answers.push(choice?.value || "");
  });

  if (!isComplete && !confirm("You have unanswered questions. Are you sure you want to submit?")) {
    return;
  }

  const score = answers.reduce((sum, answer, index) => sum + (answer === state.quizQuestions[index].answer ? 1 : 0), 0);
  const total = state.quizQuestions.length;
  
  // Display result inline
  byId("quiz-result").innerHTML = `
    <div class="status" style="margin-top: 1rem; padding: 1rem; background: var(--bg-highlight); border-radius: 8px; text-align: center;">
      <h3 style="margin: 0 0 0.5rem 0;">Your Score</h3>
      <div style="font-size: 2rem; font-weight: 700; color: var(--primary);">${score} / ${total}</div>
      <div style="color: var(--muted);">${Math.round((score / total) * 100)}%</div>
    </div>
  `;
  
  // Highlight correct and incorrect answers
  state.quizQuestions.forEach((question, index) => {
    const selectedChoice = answers[index];
    const correctChoice = question.answer;
    
    // Disable all inputs
    const inputs = document.querySelectorAll(`input[name="q-${index}"]`);
    inputs.forEach(input => input.disabled = true);
    
    if (selectedChoice === correctChoice) {
      // Correct
      const label = document.querySelector(`input[name="q-${index}"][value="${selectedChoice}"]`).closest('label');
      label.style.background = 'rgba(16, 185, 129, 0.1)'; // green tint
      label.style.border = '1px solid #10b981';
    } else {
      // Incorrect
      if (selectedChoice) {
        const label = document.querySelector(`input[name="q-${index}"][value="${selectedChoice}"]`).closest('label');
        label.style.background = 'rgba(239, 68, 68, 0.1)'; // red tint
        label.style.border = '1px solid #ef4444';
      }
      
      // Show correct answer
      const correctLabel = document.querySelector(`input[name="q-${index}"][value="${correctChoice}"]`).closest('label');
      correctLabel.style.background = 'rgba(16, 185, 129, 0.1)';
      correctLabel.style.border = '1px solid #10b981';
    }
  });

  byId("submit-quiz-btn").style.display = "none";
  showToast("Quiz submitted!", "success");
}

async function loadPage() {
  if (!docId) {
    showToast("No document selected", "error");
    return;
  }
  
  byId("loading-state").style.display = "grid";
  byId("quiz-container").style.display = "none";

  try {
    await loadDocMeta();
    await loadQuiz();
  } catch (err) {
    byId("loading-state").style.display = "none";
    showToast(err.message, "error");
    byId("doc-title").textContent = "Error";
    byId("doc-meta").textContent = err.message;
  }
}

function bindEvents() {
  byId("submit-quiz-btn").addEventListener("click", submitQuiz);
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
    }
  },
});

bindEvents();
