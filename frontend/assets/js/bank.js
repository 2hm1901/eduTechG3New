import { api, escapeHtml, showToast } from "./api.js";
import { bindAuth } from "./auth.js";

const state = {
  docs: [],
};

function byId(id) {
  return document.getElementById(id);
}

function renderDocs() {
  const host = byId("docs-list");
  if (!state.docs.length) {
    host.innerHTML = '<div class="empty">No files yet. Upload a document to get started.</div>';
    return;
  }

  host.innerHTML = state.docs
    .map((doc) => {
      return `
        <div class="doc-row doc-row-clickable" data-doc-id="${escapeHtml(doc.doc_id)}">
          <div class="doc-row-main">
            <h4>${escapeHtml(doc.filename)}</h4>
            <div class="muted small mono">${escapeHtml(doc.doc_id.slice(0, 8))}</div>
          </div>
          <div class="doc-actions">
            <a class="chip" href="/pages/doc-workspace.html?doc=${encodeURIComponent(doc.doc_id)}">Open →</a>
            <button class="chip" type="button" data-action="delete" data-doc-id="${escapeHtml(doc.doc_id)}">Delete</button>
          </div>
        </div>
      `;
    })
    .join("");
}

async function loadBank() {
  const [docsResult, health] = await Promise.all([
    api("/api/bank/documents"),
    api("/health"),
  ]);
  state.docs = docsResult.docs || [];
  renderDocs();
  byId("status-pills").innerHTML = Object.entries(health.backends)
    .map(([key, value]) => `<span class="chip">${escapeHtml(`${key}: ${value}`)}</span>`)
    .join("");
}

async function handleUpload(file) {
  byId("upload-note").textContent = `Uploading ${file.name}...`;
  try {
    // 1. Get presigned URL
    const presign = await api("/upload-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        contentType: file.type || "application/octet-stream",
      }),
    });

    const { uploadUrl, key, docId } = presign;

    // 2. Upload directly to S3
    const baseUrl = window.API_BASE_URL || "";
    const finalUploadUrl = uploadUrl.startsWith("http") ? uploadUrl : baseUrl + uploadUrl;

    const uploadResponse = await fetch(finalUploadUrl, {
      method: "PUT",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file,
    });

    if (!uploadResponse.ok) {
      throw new Error("Failed to upload file to S3");
    }

    // 3. Finalize upload
    await api("/api/bank/documents/upload/finalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        docId: docId,
        filename: file.name,
        key: key,
        size: file.size,
      }),
    });

    showToast(`Uploaded ${file.name}`, "success");
    byId("upload-note").textContent = `${file.name} uploaded`;
    await loadBank();
  } catch (error) {
    console.error("Upload error:", error);
    byId("upload-note").textContent = error.message;
    showToast(error.message, "error");
  }
}

function bindEvents() {
  const fileInput = byId("upload-input");
  byId("browse-upload").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (file) {
      handleUpload(file);
    }
  });

  const dropzone = byId("dropzone");
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("drag");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag");
    const [file] = event.dataTransfer.files;
    if (file) {
      handleUpload(file);
    }
  });

  byId("docs-list").addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest('[data-action="delete"]');
    if (!button) return;
    const docId = button.getAttribute("data-doc-id");
    if (!docId) return;
    if (!window.confirm("Delete this document?")) return;
    try {
      await api(`/api/bank/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
      showToast("Document deleted", "success");
      await loadBank();
    } catch (error) {
      showToast(error.message, "error");
    }
  });
}

bindAuth({
  onAuthChange: async (userId) => {
    if (!userId) {
      byId("docs-list").innerHTML = '<div class="empty">Sign in to view your bank.</div>';
      return;
    }
    try {
      await loadBank();
    } catch (error) {
      showToast(error.message, "error");
    }
  },
});

bindEvents();
