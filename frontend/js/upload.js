/**
 * FormWise AI - Document Upload & Extraction Service
 * Handles drag-and-drop file selection, validation, Firebase ID token auth,
 * XMLHttpRequest upload progress tracking, and authenticated document text extraction.
 */

// 1. Import shared Firebase instance (no duplicate initialization)
import { auth } from "./firebase.js";

// 2. Import Auth state observer
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js";
import { logoutUser } from "./auth.js";

// Backend API Endpoints
// Resolve API base URL dynamically.
// 1. If explicit window.FORMWISE_API_URL is configured, use it.
// 2. When frontend is served on port 5500, 8000, 3000, or 5173 (typical static dev servers),
//    route backend requests to Flask on port 5000 of the same hostname.
// 3. When frontend is served directly through Flask (same origin/port or reverse proxy),
//    use window.location.origin.
const API_BASE_URL = window.FORMWISE_API_URL || (
  ["5500", "8000", "3000", "5173"].includes(window.location.port)
    ? `${window.location.protocol}//${window.location.hostname}:5000`
    : window.location.origin
);
const UPLOAD_API_URL = `${API_BASE_URL}/api/upload`;
const EXTRACT_API_URL = `${API_BASE_URL}/api/extract`;

// Constraints
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
const ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"];

// DOM Element References
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const browseBtn = document.getElementById("browseBtn");
const selectedFileBox = document.getElementById("selectedFileBox");
const fileNameDisplay = document.getElementById("fileNameDisplay");
const fileSizeDisplay = document.getElementById("fileSizeDisplay");
const fileIcon = document.getElementById("fileIcon");
const removeFileBtn = document.getElementById("removeFileBtn");
const uploadBtn = document.getElementById("uploadBtn");
const progressSection = document.getElementById("progressSection");
const progressFill = document.getElementById("progressFill");
const progressPercent = document.getElementById("progressPercent");
const progressStatusText = document.getElementById("progressStatusText");
const successBanner = document.getElementById("successBanner");
const successMessage = document.getElementById("successMessage");
const documentIdDisplay = document.getElementById("documentIdDisplay");
const errorBanner = document.getElementById("errorBanner");
const errorMessage = document.getElementById("errorMessage");
const uploadAnotherBtn = document.getElementById("uploadAnotherBtn");
const extractBtn = document.getElementById("extractBtn");
const proceedAssistantBtn = document.getElementById("proceedAssistantBtn");
const logoutBtn = document.getElementById("logoutBtn");
const headerDisplayName = document.getElementById("headerDisplayName");
const headerAvatar = document.getElementById("headerAvatar");

// Extraction Section Elements
const extractionSection = document.getElementById("extractionSection");
const extractionLoading = document.getElementById("extractionLoading");
const extractionContent = document.getElementById("extractionContent");
const extractedTextArea = document.getElementById("extractedTextArea");
const badgeFileType = document.getElementById("badgeFileType");
const badgePageCount = document.getElementById("badgePageCount");
const badgeWordCount = document.getElementById("badgeWordCount");
const extractionProceedBtn = document.getElementById("extractionProceedBtn");

// State
let selectedFile = null;
let currentXhr = null;
let uploadedDocumentId = null;

/**
 * Format bytes into human-readable units (KB, MB).
 */
function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

/**
 * Show error message banner.
 */
function showError(message) {
  if (errorMessage) errorMessage.textContent = message;
  if (errorBanner) errorBanner.style.display = "flex";
  if (successBanner) successBanner.style.display = "none";
}

/**
 * Show success message banner with Document ID.
 */
function showSuccess(data) {
  uploadedDocumentId = data.document_id || null;

  if (documentIdDisplay) {
    documentIdDisplay.textContent = uploadedDocumentId || "N/A";
  }
  if (successMessage) {
    successMessage.textContent = `File "${data.filename || "document"}" was validated and saved securely.`;
  }
  if (successBanner) successBanner.style.display = "flex";
  if (errorBanner) errorBanner.style.display = "none";

  // Connect proceeding button to AI Assistant with doc_id parameter
  if (proceedAssistantBtn && uploadedDocumentId) {
    proceedAssistantBtn.href = `assistant.html?doc_id=${encodeURIComponent(uploadedDocumentId)}`;
  }
  if (extractionProceedBtn && uploadedDocumentId) {
    extractionProceedBtn.href = `assistant.html?doc_id=${encodeURIComponent(uploadedDocumentId)}`;
  }

  // Ensure Extract Text button is ready
  if (extractBtn) {
    extractBtn.disabled = !uploadedDocumentId;
    extractBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="margin-right: 6px;">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="16" y1="13" x2="8" y2="13"></line>
        <line x1="16" y1="17" x2="8" y2="17"></line>
        <polyline points="10 9 9 9 8 9"></polyline>
      </svg>
      Extract Text
    `;
  }
}

/**
 * Clear status notification banners.
 */
function clearBanners() {
  if (errorBanner) errorBanner.style.display = "none";
  if (successBanner) successBanner.style.display = "none";
}

/**
 * Update header with student profile details.
 */
function updateHeaderProfile(user) {
  const name = user.displayName || user.email.split("@")[0] || "Student";
  if (headerDisplayName) headerDisplayName.textContent = name;
  if (headerAvatar) headerAvatar.textContent = name.charAt(0).toUpperCase();
}

/**
 * Validate a candidate file.
 * Returns true if valid, false otherwise (displays error).
 */
function validateFile(file) {
  clearBanners();

  if (!file) {
    showError("No file selected.");
    return false;
  }

  // 1. Check for empty file
  if (file.size === 0) {
    showError("The selected file is empty (0 bytes). Please choose a valid document.");
    return false;
  }

  // 2. Check maximum size (10 MB)
  if (file.size > MAX_FILE_SIZE_BYTES) {
    showError(`File size (${formatFileSize(file.size)}) exceeds the maximum allowed limit of 10 MB.`);
    return false;
  }

  // 3. Check file extension
  const fileName = file.name || "";
  const ext = fileName.includes(".") ? fileName.split(".").pop().toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    showError(`Unsupported file format (.${ext || "unknown"}). Allowed formats: PDF, JPG, JPEG, PNG.`);
    return false;
  }

  return true;
}

/**
 * Handle file selection from browse or drop zone.
 */
function handleFileSelection(file) {
  if (!validateFile(file)) {
    resetFileSelection();
    return;
  }

  selectedFile = file;

  // Display file metadata
  if (fileNameDisplay) fileNameDisplay.textContent = file.name;
  if (fileSizeDisplay) fileSizeDisplay.textContent = formatFileSize(file.size);

  // Update icon based on file type
  if (fileIcon) {
    const isPdf = file.name.toLowerCase().endsWith(".pdf");
    fileIcon.innerHTML = isPdf
      ? `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`
      : `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`;
  }

  // Reveal preview box and enable upload button
  if (selectedFileBox) selectedFileBox.style.display = "flex";
  if (uploadBtn) {
    uploadBtn.disabled = false;
    uploadBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="17 8 12 3 7 8"></polyline>
        <line x1="12" y1="3" x2="12" y2="15"></line>
      </svg>
      Upload Document
    `;
  }
}

/**
 * Reset selected file state.
 */
function resetFileSelection() {
  selectedFile = null;
  if (fileInput) fileInput.value = "";
  if (selectedFileBox) selectedFileBox.style.display = "none";
  if (uploadBtn) uploadBtn.disabled = true;
  if (progressSection) progressSection.style.display = "none";
  if (progressFill) progressFill.style.width = "0%";
}

/**
 * Upload selected file using XMLHttpRequest for real-time progress tracking.
 */
async function uploadSelectedFile() {
  if (!selectedFile) {
    showError("Please select a file to upload.");
    return;
  }

  clearBanners();

  // 1. Verify user authentication & get Firebase ID token
  const currentUser = auth.currentUser;
  if (!currentUser) {
    showError("Your session has expired. Redirecting to login...");
    setTimeout(() => window.location.replace("login.html"), 1500);
    return;
  }

  let idToken = "";
  try {
    idToken = await currentUser.getIdToken();
  } catch (tokenErr) {
    console.error("Error retrieving Firebase ID token:", tokenErr);
    showError("Could not retrieve authentication credentials. Please re-login.");
    return;
  }

  // 2. Prepare FormData
  const formData = new FormData();
  formData.append("file", selectedFile);

  // 3. UI: Prepare progress bar
  if (progressSection) progressSection.style.display = "block";
  if (progressFill) progressFill.style.width = "0%";
  if (progressPercent) progressPercent.textContent = "0%";
  if (progressStatusText) progressStatusText.textContent = "Uploading document...";

  if (uploadBtn) {
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = `Uploading...`;
  }

  // 4. Send via XMLHttpRequest
  currentXhr = new XMLHttpRequest();
  currentXhr.open("POST", UPLOAD_API_URL, true);

  // Add Authorization header
  currentXhr.setRequestHeader("Authorization", `Bearer ${idToken}`);

  // Upload Progress Event
  currentXhr.upload.onprogress = (event) => {
    if (event.lengthComputable) {
      const percentComplete = Math.round((event.loaded / event.total) * 100);
      if (progressFill) progressFill.style.width = `${percentComplete}%`;
      if (progressPercent) progressPercent.textContent = `${percentComplete}%`;

      if (percentComplete === 100 && progressStatusText) {
        progressStatusText.textContent = "Processing and validating document...";
      }
    }
  };

  // Upload Complete Event
  currentXhr.onload = () => {
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.innerHTML = `Upload Document`;
    }

    let response = {};
    try {
      response = JSON.parse(currentXhr.responseText);
    } catch (e) {
      response = {};
    }

    if (currentXhr.status === 201 || currentXhr.status === 200) {
      showSuccess(response);
      resetFileSelection();
    } else {
      const errMsg = response.error || `Server responded with status code ${currentXhr.status}`;
      showError(errMsg);
      if (progressSection) progressSection.style.display = "none";
    }
  };

  // Upload Network Error Event
  currentXhr.onerror = () => {
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.innerHTML = `Upload Document`;
    }
    if (progressSection) progressSection.style.display = "none";
    showError("Network error connecting to Flask backend. Please ensure the backend server is running at http://localhost:5000.");
  };

  currentXhr.send(formData);
}

/**
 * Authenticated Document Text Extraction Flow
 * Sends POST /api/extract with { "document_id": uploadedDocumentId }
 * Uses textarea.value to safely populate extracted content without innerHTML.
 */
async function extractDocumentText() {
  if (!uploadedDocumentId) {
    showError("No uploaded document ID available for extraction. Please upload a file first.");
    return;
  }

  clearBanners();

  // 1. Verify user authentication & get fresh Firebase ID token
  const currentUser = auth.currentUser;
  if (!currentUser) {
    showError("Your session has expired. Redirecting to login...");
    setTimeout(() => window.location.replace("login.html"), 1500);
    return;
  }

  let idToken = "";
  try {
    idToken = await currentUser.getIdToken();
  } catch (tokenErr) {
    console.error("Error retrieving Firebase ID token:", tokenErr);
    showError("Could not retrieve authentication credentials. Please re-login.");
    return;
  }

  // 2. Set UI loading state
  if (extractBtn) {
    extractBtn.disabled = true;
    extractBtn.innerHTML = `
      <span class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0 6px 0 0; display: inline-block; vertical-align: middle;"></span>
      Extracting...
    `;
  }

  if (extractionSection) extractionSection.style.display = "block";
  if (extractionLoading) extractionLoading.style.display = "block";
  if (extractionContent) extractionContent.style.display = "none";

  // Scroll smoothly to extraction section
  extractionSection.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const response = await fetch(EXTRACT_API_URL, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${idToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: uploadedDocumentId
      })
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || `Server responded with status code ${response.status}`);
    }

    // 3. Render metadata badges safely via textContent
    if (badgeFileType) {
      badgeFileType.textContent = `Format: ${data.file_type || "N/A"}`;
    }
    if (badgePageCount) {
      badgePageCount.textContent = `Pages: ${data.page_count ?? 1}`;
    }
    if (badgeWordCount) {
      badgeWordCount.textContent = `Words: ${data.word_count ?? 0}`;
    }

    // 4. Safely set extracted text using textarea.value (NEVER innerHTML)
    if (extractedTextArea) {
      extractedTextArea.value = data.full_text || "";
    }

    // 5. Reveal content area and hide loader
    if (extractionLoading) extractionLoading.style.display = "none";
    if (extractionContent) extractionContent.style.display = "block";

    // 6. Reset Extract button
    if (extractBtn) {
      extractBtn.disabled = false;
      extractBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="margin-right: 6px;">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        Re-Extract
      `;
    }

  } catch (err) {
    console.error("Text extraction failed:", err);
    showError(err.message || "An error occurred while extracting document text.");

    if (extractionLoading) extractionLoading.style.display = "none";
    if (extractionSection) extractionSection.style.display = "none";

    if (extractBtn) {
      extractBtn.disabled = false;
      extractBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="margin-right: 6px;">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
        Extract Text
      `;
    }
  }
}

// ============================================================================
// Drag and Drop Event Handlers
// ============================================================================
if (dropZone) {
  // Prevent browser default open file behavior
  ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });

  // Highlight drop zone on drag over
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, () => {
      dropZone.classList.add("drag-over");
    });
  });

  // Remove highlight on drag leave or drop
  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, () => {
      dropZone.classList.remove("drag-over");
    });
  });

  // Handle dropped files
  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      handleFileSelection(dt.files[0]);
    }
  });

  // Clicking on drop zone triggers file input
  dropZone.addEventListener("click", () => {
    if (fileInput) fileInput.click();
  });
}

// Browse Button click
if (browseBtn) {
  browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (fileInput) fileInput.click();
  });
}

// Native File Input change
if (fileInput) {
  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelection(e.target.files[0]);
    }
  });
}

// Remove File button click
if (removeFileBtn) {
  removeFileBtn.addEventListener("click", () => {
    resetFileSelection();
    clearBanners();
  });
}

// Upload Button click
if (uploadBtn) {
  uploadBtn.addEventListener("click", uploadSelectedFile);
}

// Extract Text Button click
if (extractBtn) {
  extractBtn.addEventListener("click", extractDocumentText);
}

// Upload Another Button click in success banner
if (uploadAnotherBtn) {
  uploadAnotherBtn.addEventListener("click", () => {
    clearBanners();
    resetFileSelection();
    uploadedDocumentId = null;
    if (extractionSection) extractionSection.style.display = "none";
    if (extractedTextArea) extractedTextArea.value = "";
  });
}

// ============================================================================
// Authentication Protection & User Session
// ============================================================================
onAuthStateChanged(auth, (user) => {
  if (user) {
    document.body.classList.add("auth-verified");
    updateHeaderProfile(user);
  } else {
    window.location.replace("login.html");
  }
});

// Logout Button Handler
if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    const result = await logoutUser();
    if (result.success) {
      window.location.replace("login.html");
    } else {
      alert("Sign out failed: " + result.message);
    }
  });
}
