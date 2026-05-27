const STORAGE_KEY = "sb_user";

export function getUserId() {
  return window.localStorage.getItem(STORAGE_KEY) || "";
}

export function setUserId(userId) {
  window.localStorage.setItem(STORAGE_KEY, userId);
}

export function clearUserId() {
  window.localStorage.removeItem(STORAGE_KEY);
}
