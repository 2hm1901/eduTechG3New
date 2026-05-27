import { api, showToast } from "./api.js";
import { clearUserId, getUserId, setUserId } from "./session.js";

export function bindAuth({ onAuthChange }) {
  const overlay = document.getElementById("auth-overlay");
  const userField = document.getElementById("auth-user");
  const passField = document.getElementById("auth-pass");
  const errorField = document.getElementById("auth-error");
  const loginBtn = document.getElementById("auth-login");
  const registerBtn = document.getElementById("auth-register");
  const logoutBtn = document.getElementById("logout-btn");
  const userLabel = document.getElementById("user-label");

  async function login() {
    const username = userField.value.trim();
    const password = passField.value;
    if (!username || !password) {
      errorField.textContent = "Fill in both fields";
      return;
    }
    try {
      const result = await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setUserId(result.user_id);
      overlay.classList.remove("open");
      if (userLabel) {
        userLabel.textContent = result.user_id;
      }
      errorField.textContent = "";
      showToast(`Signed in as ${result.user_id}`, "success");
      onAuthChange?.(result.user_id);
    } catch (error) {
      errorField.textContent = error.message;
    }
  }

  async function register() {
    const username = userField.value.trim();
    const password = passField.value;
    if (!username || !password) {
      errorField.textContent = "Fill in both fields";
      return;
    }
    try {
      const result = await api("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setUserId(result.user_id);
      overlay.classList.remove("open");
      if (userLabel) {
        userLabel.textContent = result.user_id;
      }
      errorField.textContent = "";
      showToast(`Created ${result.user_id}`, "success");
      onAuthChange?.(result.user_id);
    } catch (error) {
      errorField.textContent = error.message;
    }
  }

  loginBtn?.addEventListener("click", login);
  registerBtn?.addEventListener("click", register);
  logoutBtn?.addEventListener("click", () => {
    clearUserId();
    overlay.classList.add("open");
    if (userLabel) {
      userLabel.textContent = "";
    }
    onAuthChange?.("");
  });
  passField?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      login();
    }
  });

  const currentUser = getUserId();
  if (currentUser) {
    overlay.classList.remove("open");
    if (userLabel) {
      userLabel.textContent = currentUser;
    }
    onAuthChange?.(currentUser);
  } else {
    overlay.classList.add("open");
  }

  window.addEventListener("studybot:unauthorized", () => {
    clearUserId();
    overlay.classList.add("open");
    if (userLabel) {
      userLabel.textContent = "";
    }
    if (errorField) {
      errorField.textContent = "Session expired. Sign in again.";
    }
    onAuthChange?.("");
  });
}
