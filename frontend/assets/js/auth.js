import { api, showToast } from "./api.js";
import { clearUserId, getUserId, setUserId, clearToken, setToken } from "./session.js";

export function bindAuth({ onAuthChange }) {
  const overlay = document.getElementById("auth-overlay");
  const userField = document.getElementById("auth-user");
  const passField = document.getElementById("auth-pass");
  const errorField = document.getElementById("auth-error");
  const loginBtn = document.getElementById("auth-login");
  const registerBtn = document.getElementById("auth-register");
  const logoutBtn = document.getElementById("logout-btn");
  const userLabel = document.getElementById("user-label");

  let userPool = null;
  let isHandlingUnauthorized = false; // Guard to prevent multiple 401 handlers

  if (typeof AmazonCognitoIdentity !== 'undefined' && window.COGNITO_USER_POOL_ID) {
    const poolData = {
      UserPoolId: window.COGNITO_USER_POOL_ID,
      ClientId: window.COGNITO_CLIENT_ID
    };
    userPool = new AmazonCognitoIdentity.CognitoUserPool(poolData);
  }

  function forceLogout(message) {
    if (userPool) {
      const currentUser = userPool.getCurrentUser();
      if (currentUser) currentUser.signOut();
    }
    clearUserId();
    clearToken();
    overlay.classList.add("open");
    if (userLabel) userLabel.textContent = "";
    if (errorField) errorField.textContent = message || "Session expired. Sign in again.";
    onAuthChange?.("");
  }

  /** Try to silently refresh the Cognito token. Returns true on success. */
  function tryRefreshToken() {
    return new Promise((resolve) => {
      if (!userPool) { resolve(false); return; }
      const cognitoUser = userPool.getCurrentUser();
      if (!cognitoUser) { resolve(false); return; }

      cognitoUser.getSession((err, session) => {
        if (err || !session || !session.isValid()) {
          resolve(false);
          return;
        }
        // Session refreshed successfully — save new token
        const newToken = session.getIdToken().getJwtToken();
        setToken(newToken);
        resolve(true);
      });
    });
  }

  function login() {
    let username = userField.value.trim();
    const password = passField.value;
    if (!username || !password) {
      errorField.textContent = "Fill in both fields";
      return;
    }
    
    // Keep original name for display
    const displayName = username.includes("@") ? username.split("@")[0] : username;
    // Auto-convert to email format for Cognito
    if (!username.includes("@")) {
      username = username + "@studybot.local";
    }

    if (!userPool) {
      errorField.textContent = "Cognito SDK is not initialized.";
      return;
    }

    const authenticationDetails = new AmazonCognitoIdentity.AuthenticationDetails({
      Username: username,
      Password: password,
    });

    const userData = {
      Username: username,
      Pool: userPool,
    };
    const cognitoUser = new AmazonCognitoIdentity.CognitoUser(userData);

    cognitoUser.authenticateUser(authenticationDetails, {
      onSuccess: function (result) {
        const idToken = result.getIdToken().getJwtToken();
        setToken(idToken);
        setUserId(displayName);
        
        overlay.classList.remove("open");
        if (userLabel) userLabel.textContent = displayName;
        errorField.textContent = "";
        isHandlingUnauthorized = false;
        // Always redirect to bank after login
        window.location.href = window.location.pathname.includes("/pages/")
          ? "bank.html"
          : "/pages/bank.html";
      },
      onFailure: function (err) {
        errorField.textContent = err.message || JSON.stringify(err);
      },
    });
  }

  function register() {
    let username = userField.value.trim();
    const password = passField.value;
    if (!username || !password) {
      errorField.textContent = "Fill in both fields";
      return;
    }

    if (!username.includes("@")) {
      username = username + "@studybot.local";
    }

    if (!userPool) {
      errorField.textContent = "Cognito SDK is not initialized.";
      return;
    }

    userPool.signUp(username, password, [], null, function (err, result) {
      if (err) {
        errorField.textContent = err.message || JSON.stringify(err);
        return;
      }
      showToast(`Created ${username}, logging in...`, "success");
      login();
    });
  }

  loginBtn?.addEventListener("click", login);
  registerBtn?.addEventListener("click", register);
  logoutBtn?.addEventListener("click", () => {
    if (userPool) {
      const cu = userPool.getCurrentUser();
      if (cu) cu.signOut();
    }
    clearUserId();
    clearToken();
    // Redirect to bank with clean state
    window.location.href = window.location.pathname.includes("/pages/")
      ? "bank.html"
      : "/pages/bank.html";
  });
  passField?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      login();
    }
  });

  // On page load: trust localStorage for immediate UI, refresh token silently in background
  const currentUser = getUserId();
  if (currentUser) {
    overlay.classList.remove("open");
    if (userLabel) userLabel.textContent = currentUser;
    onAuthChange?.(currentUser);

    // Silently try to refresh Cognito token in background (no UI impact if it fails)
    if (userPool) {
      const cognitoUser = userPool.getCurrentUser();
      if (cognitoUser) {
        cognitoUser.getSession((err, session) => {
          if (!err && session && session.isValid()) {
            setToken(session.getIdToken().getJwtToken());
          }
          // If refresh fails, do nothing — let 401 handler deal with it later
        });
      }
    }
  } else {
    overlay.classList.add("open");
  }

  // Handle 401 from API calls — debounced so it only fires once
  window.addEventListener("studybot:unauthorized", async () => {
    if (isHandlingUnauthorized) return; // Already handling, skip duplicates
    isHandlingUnauthorized = true;

    // Try silent refresh first
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      isHandlingUnauthorized = false;
      // Reload page to retry with new token
      window.location.reload();
      return;
    }

    // Refresh failed — redirect to bank with login form
    forceLogout("Session expired. Sign in again.");
    window.location.href = window.location.pathname.includes("/pages/")
      ? "bank.html"
      : "/pages/bank.html";
  });
}
