/**
 * FormWise AI - AI Assistant & Smart Validation Controller
 * Manages document analysis via Gemini API, reading doc_id from query params,
 * student answer inputs, Firestore profile autofill, and authenticated form validation (POST /api/validate).
 * Safe DOM manipulation only (XSS-free, zero innerHTML for user/AI content).
 */

import { auth, db } from "./firebase.js";
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js";
import { doc, getDoc } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-firestore.js";
import { logoutUser } from "./auth.js";

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
const ANALYSE_API_URL = `${API_BASE_URL}/api/analyse`;
const VALIDATE_API_URL = `${API_BASE_URL}/api/validate`;

// ---------------------------------------------------------------------------
// Phase 7 Step 5 – Checklist & Readiness API URLs
// ---------------------------------------------------------------------------
const CHECKLIST_API_URL    = `${API_BASE_URL}/api/checklist`;
const CHECKLIST_CONFIRM_URL = `${API_BASE_URL}/api/checklist/confirm`;
const READINESS_API_URL    = `${API_BASE_URL}/api/readiness`;

// ---------------------------------------------------------------------------
// DOM References
// ---------------------------------------------------------------------------
const headerDisplayName = document.getElementById("headerDisplayName");
const headerAvatar = document.getElementById("headerAvatar");
const logoutBtn = document.getElementById("logoutBtn");
const noDocBanner = document.getElementById("noDocBanner");
const errorBanner = document.getElementById("errorBanner");
const errorMessage = document.getElementById("errorMessage");
const displayDocId = document.getElementById("displayDocId");
const languageSelect = document.getElementById("languageSelect");
const analyseBtn = document.getElementById("analyseBtn");
const loadingCard = document.getElementById("loadingCard");
const overviewCard = document.getElementById("overviewCard");
const formTitleDisplay = document.getElementById("formTitleDisplay");
const fileTypeBadge = document.getElementById("fileTypeBadge");
const pageCountBadge = document.getElementById("pageCountBadge");
const wordCountBadge = document.getElementById("wordCountBadge");
const summaryEnglishBox = document.getElementById("summaryEnglishBox");
const summaryEnglishText = document.getElementById("summaryEnglishText");
const summaryTamilBox = document.getElementById("summaryTamilBox");
const summaryTamilText = document.getElementById("summaryTamilText");
const generalTipsBox = document.getElementById("generalTipsBox");
const tipsContent = document.getElementById("tipsContent");
const fieldsSection = document.getElementById("fieldsSection");
const fieldsCountBadge = document.getElementById("fieldsCountBadge");
const fieldsGrid = document.getElementById("fieldsGrid");

// Validation Interface DOM Elements
const autofillBtn = document.getElementById("autofillBtn");
const autofillBanner = document.getElementById("autofillBanner");
const autofillBannerText = document.getElementById("autofillBannerText");
const validateBtnTop = document.getElementById("validateBtnTop");
const validateBtnBottom = document.getElementById("validateBtnBottom");

const validationSummaryCard = document.getElementById("validationSummaryCard");
const summaryStatusBadge = document.getElementById("summaryStatusBadge");
const summaryDescription = document.getElementById("summaryDescription");
const metricTotalFields = document.getElementById("metricTotalFields");
const metricCompleted = document.getElementById("metricCompleted");
const metricMissingReq = document.getElementById("metricMissingReq");
const metricErrors = document.getElementById("metricErrors");

// ---------------------------------------------------------------------------
// Application State
// ---------------------------------------------------------------------------
let currentDocId = null;
let lastAnalysisData = null;
const studentAnswers = {};       // { [fieldId]: string }
let validationResults = null;    // { [fieldId]: fieldResultObject }
let overallValidation = null;    // overall validation response from backend
let isSubmittingValidation = false;

// ---------------------------------------------------------------------------
// Phase 7 Step 5 – Checklist & Readiness State
// ---------------------------------------------------------------------------
let isLoadingChecklist      = false;
let isSubmittingConfirmation = false;
let isLoadingReadiness      = false;
let lastChecklistData       = null;  // stores last /api/checklist response
let lastReadinessData       = null;  // stores last /api/readiness response

// Phase 7 Step 5 – DOM References (resolved lazily when cards are needed)
function getChecklistCard()      { return document.getElementById("checklistCard"); }
function getChecklistMetaRow()   { return document.getElementById("checklistMetaRow"); }
function getChecklistItems()     { return document.getElementById("checklistItems"); }
function getReadinessCard()      { return document.getElementById("readinessCard"); }
function getReadinessScore()     { return document.getElementById("readinessScoreNumber"); }
function getReadinessStatus()    { return document.getElementById("readinessStatusPill"); }
function getReadinessBreakdown() { return document.getElementById("readinessBreakdownGrid"); }
function getReadinessActions()   { return document.getElementById("readinessActionsBlock"); }

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function getDocIdFromURL() {
  const params = new URLSearchParams(window.location.search);
  return params.get("doc_id") || params.get("document_id");
}

function showError(msg) {
  if (errorMessage) errorMessage.textContent = msg;
  if (errorBanner) {
    errorBanner.style.display = "flex";
    errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function clearError() {
  if (errorBanner) errorBanner.style.display = "none";
}

function updateHeaderProfile(user) {
  const name = user.displayName || user.email.split("@")[0] || "Student";
  if (headerDisplayName) headerDisplayName.textContent = name;
  if (headerAvatar) headerAvatar.textContent = name.charAt(0).toUpperCase();
}

/**
 * Safely creates a DOM element without using innerHTML.
 */
function createEl(tag, className = "", textContent = "") {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (textContent) el.textContent = textContent;
  return el;
}

// ---------------------------------------------------------------------------
// Render Validation Summary
// ---------------------------------------------------------------------------
function renderValidationSummary() {
  if (!validationSummaryCard || !overallValidation) {
    if (validationSummaryCard) validationSummaryCard.style.display = "none";
    return;
  }

  validationSummaryCard.style.display = "block";

  if (metricTotalFields) metricTotalFields.textContent = String(overallValidation.total_fields ?? 0);
  if (metricCompleted) metricCompleted.textContent = String(overallValidation.completed_fields ?? 0);
  if (metricMissingReq) metricMissingReq.textContent = String(overallValidation.missing_required_count ?? 0);
  if (metricErrors) metricErrors.textContent = String(overallValidation.error_count ?? 0);

  validationSummaryCard.classList.remove("has-errors", "all-valid");
  if (summaryStatusBadge) summaryStatusBadge.className = "badge-status";

  if (overallValidation.is_valid) {
    validationSummaryCard.classList.add("all-valid");
    if (summaryStatusBadge) {
      summaryStatusBadge.classList.add("valid");
      summaryStatusBadge.textContent = "✓ All Valid";
    }
    if (summaryDescription) {
      summaryDescription.textContent = "All required fields are completed and valid. Your form is ready for submission!";
    }
  } else {
    validationSummaryCard.classList.add("has-errors");
    const count = overallValidation.error_count || 1;
    if (summaryStatusBadge) {
      summaryStatusBadge.classList.add("error");
      summaryStatusBadge.textContent = `⚠ ${count} Issue${count === 1 ? "" : "s"} Found`;
    }
    if (summaryDescription) {
      const missing = overallValidation.missing_required_count || 0;
      summaryDescription.textContent = `Please review and correct the highlighted fields below (${missing} required field${missing === 1 ? " is" : "s are"} empty or invalid).`;
    }
  }
}

// ---------------------------------------------------------------------------
// Render Structured Field Analysis & Answer Inputs
// ---------------------------------------------------------------------------
function renderAnalysisResults(data, requestedLanguage) {
  lastAnalysisData = data;
  const analysis = data.analysis || {};
  const fields = analysis.fields || [];

  // 1. Overview Metadata
  if (formTitleDisplay) {
    formTitleDisplay.textContent = analysis.form_title || "Application Form";
  }
  if (fileTypeBadge) {
    fileTypeBadge.textContent = `Format: ${data.file_type || "PDF"}`;
  }
  if (pageCountBadge) {
    pageCountBadge.textContent = `${data.page_count ?? 1} Page${(data.page_count ?? 1) > 1 ? "s" : ""}`;
  }
  if (wordCountBadge) {
    wordCountBadge.textContent = `${data.word_count ?? 0} Words`;
  }

  // 2. Summary (English)
  if (analysis.summary_english && (requestedLanguage === "english" || requestedLanguage === "both")) {
    if (summaryEnglishText) summaryEnglishText.textContent = analysis.summary_english;
    if (summaryEnglishBox) summaryEnglishBox.style.display = "block";
  } else if (summaryEnglishBox) {
    summaryEnglishBox.style.display = "none";
  }

  // 3. Summary (Tamil)
  if (analysis.summary_tamil && (requestedLanguage === "tamil" || requestedLanguage === "both")) {
    if (summaryTamilText) summaryTamilText.textContent = analysis.summary_tamil;
    if (summaryTamilBox) summaryTamilBox.style.display = "block";
  } else if (summaryTamilBox) {
    summaryTamilBox.style.display = "none";
  }

  // 4. General Tips
  const tips = (requestedLanguage === "tamil")
    ? (analysis.general_tips_tamil || "")
    : (analysis.general_tips_english || analysis.general_tips_tamil || "");

  if (tips && tipsContent && generalTipsBox) {
    tipsContent.textContent = tips;
    generalTipsBox.style.display = "block";
  } else if (generalTipsBox) {
    generalTipsBox.style.display = "none";
  }

  if (overviewCard) overviewCard.style.display = "block";

  // 5. Render Validation Summary Card if available
  renderValidationSummary();

  // 6. Fields Breakdown with Answer Inputs
  if (fieldsGrid) {
    fieldsGrid.innerHTML = ""; // Clear existing cards safely
  }

  if (fieldsCountBadge) {
    fieldsCountBadge.textContent = `${fields.length} Field${fields.length === 1 ? "" : "s"} Found`;
  }

  fields.forEach((field, index) => {
    const fieldId = String(field.field_id || field.field_name || `field_${index + 1}`);
    const isRequired = Boolean(field.is_required);
    const fieldType = String(field.field_type || "text").toLowerCase();

    const card = createEl("div", "field-card");
    card.id = `card_${fieldId}`;

    // Apply status styling if validation results exist
    const fieldValidation = validationResults ? validationResults[fieldId] : null;
    if (fieldValidation) {
      if (fieldValidation.status === "valid") {
        card.classList.add("status-valid");
      } else if (fieldValidation.status === "error") {
        card.classList.add("status-error");
      } else if (fieldValidation.status === "warning") {
        card.classList.add("status-warning");
      }
    }

    // --- Header: Number + Question + Name tag + Required/Status Badge ---
    const header = createEl("div", "field-header");
    const num = createEl("div", "field-number", String(index + 1));
    const titleArea = createEl("div", "field-title-area");
    const question = createEl("div", "field-question", field.question || `Question ${index + 1}`);
    const nameTag = createEl("span", "field-name-tag", field.field_name || fieldId);

    titleArea.appendChild(question);
    titleArea.appendChild(nameTag);
    header.appendChild(num);
    header.appendChild(titleArea);

    // Requirement or Validation Status Badge
    if (fieldValidation) {
      const statusBadge = createEl("span", `badge-status ${fieldValidation.status}`);
      if (fieldValidation.status === "valid") {
        statusBadge.textContent = "✓ Valid";
      } else if (fieldValidation.status === "error") {
        statusBadge.textContent = fieldValidation.errors?.includes("required_empty")
          ? "⚠ Required – Missing"
          : "⚠ Needs Correction";
      } else if (fieldValidation.status === "warning") {
        statusBadge.textContent = "Optional – Blank";
      }
      header.appendChild(statusBadge);
    } else {
      if (isRequired) {
        const reqBadge = createEl("span", "badge-required", "Required *");
        header.appendChild(reqBadge);
      } else {
        const optBadge = createEl("span", "badge-optional", "Optional");
        header.appendChild(optBadge);
      }
    }

    card.appendChild(header);

    // --- Content Block: Guidance & Explanations ---
    const contentBlock = createEl("div", "field-content-block");

    // What to fill
    if (field.what_to_fill) {
      const row = createEl("div", "info-row");
      row.appendChild(createEl("span", "info-label", "What information is needed:"));
      row.appendChild(createEl("div", "info-value", field.what_to_fill));
      contentBlock.appendChild(row);
    }

    // English Explanation
    if (field.explanation_english && (requestedLanguage === "english" || requestedLanguage === "both")) {
      const row = createEl("div", "info-row");
      row.appendChild(createEl("span", "info-label", "Explanation (English):"));
      const box = createEl("div", "explanation-box english", field.explanation_english);
      row.appendChild(box);
      contentBlock.appendChild(row);
    }

    // Tamil Explanation
    if (field.explanation_tamil && (requestedLanguage === "tamil" || requestedLanguage === "both")) {
      const row = createEl("div", "info-row");
      row.appendChild(createEl("span", "info-label", "விளக்கம் (Tamil):"));
      const box = createEl("div", "explanation-box tamil", field.explanation_tamil);
      row.appendChild(box);
      contentBlock.appendChild(row);
    }

    // Example Value (Fictional note)
    if (field.example) {
      const row = createEl("div", "info-row");
      row.appendChild(createEl("span", "info-label", "Example Value (fictional — do not copy):"));
      const pill = createEl("div", "example-pill", field.example);
      row.appendChild(pill);
      contentBlock.appendChild(row);
    }

    // --- Answer Input Section ---
    const answerSection = createEl("div", "answer-section");

    const answerLabelRow = createEl("div", "answer-label-row");
    const answerLabel = createEl("label", "answer-label", "Your Answer:");
    answerLabel.htmlFor = `input_${fieldId}`;

    const typeHint = createEl(
      "span",
      "field-name-tag",
      fieldType === "email" ? "Email format" :
      fieldType === "phone" ? "10-digit Indian Mobile" :
      fieldType === "date" ? "Date (YYYY-MM-DD)" :
      fieldType === "number" ? "Numeric digits" : "Text"
    );
    answerLabelRow.appendChild(answerLabel);
    answerLabelRow.appendChild(typeHint);
    answerSection.appendChild(answerLabelRow);

    // Create appropriate input element based on field_type
    let inputEl;
    const isLongText = fieldType === "text" && (
      fieldId.includes("address") ||
      (field.question && field.question.toLowerCase().includes("address"))
    );

    if (isLongText) {
      inputEl = document.createElement("textarea");
      inputEl.rows = 3;
      inputEl.placeholder = "Enter your complete address...";
    } else {
      inputEl = document.createElement("input");
      if (fieldType === "email") {
        inputEl.type = "email";
        inputEl.placeholder = "e.g. name@example.com";
      } else if (fieldType === "phone") {
        inputEl.type = "tel";
        inputEl.placeholder = "e.g. 9876543210 (10 digits)";
      } else if (fieldType === "date") {
        inputEl.type = "date";
      } else if (fieldType === "number") {
        inputEl.type = "number";
        inputEl.placeholder = "Enter number...";
      } else {
        inputEl.type = "text";
        inputEl.placeholder = "Enter your answer...";
      }
    }

    inputEl.id = `input_${fieldId}`;
    inputEl.name = fieldId;
    inputEl.className = "answer-input";

    // IMPORTANT ANSWER SAFETY:
    // 1. NEVER prefill inputs using Gemini's fictional example values!
    // 2. Only populate with previously entered student answer, if present.
    if (studentAnswers[fieldId] !== undefined) {
      inputEl.value = studentAnswers[fieldId];
    } else {
      inputEl.value = "";
    }

    // Apply error/valid styling to the input
    if (fieldValidation) {
      if (fieldValidation.status === "error") {
        inputEl.classList.add("input-error");
      } else if (fieldValidation.status === "valid") {
        inputEl.classList.add("input-valid");
      }
    }

    // Event listener: store student answer in real-time
    inputEl.addEventListener("input", (e) => {
      studentAnswers[fieldId] = e.target.value;
      inputEl.classList.remove("input-error");
    });

    answerSection.appendChild(inputEl);

    // --- Validation Feedback Section ---
    if (fieldValidation) {
      const feedbackBox = createEl("div", `validation-feedback-box ${fieldValidation.status}`);

      if (fieldValidation.status === "error") {
        const strong = createEl("strong", "", "Needs attention: ");
        feedbackBox.appendChild(strong);

        // Display English suggestion if applicable
        if (fieldValidation.suggestions_en && (requestedLanguage === "english" || requestedLanguage === "both")) {
          const enMsg = createEl("div", "", fieldValidation.suggestions_en);
          enMsg.style.marginTop = "4px";
          feedbackBox.appendChild(enMsg);
        }

        // Display Tamil suggestion if applicable
        if (fieldValidation.suggestions_ta && (requestedLanguage === "tamil" || requestedLanguage === "both")) {
          const taMsg = createEl("div", "", fieldValidation.suggestions_ta);
          taMsg.style.marginTop = "4px";
          taMsg.style.fontWeight = "500";
          feedbackBox.appendChild(taMsg);
        }

      } else if (fieldValidation.status === "warning") {
        feedbackBox.textContent = "This optional field is currently blank. You may fill it in or leave it as-is.";
      } else if (fieldValidation.status === "valid") {
        feedbackBox.textContent = "✓ Field format is valid.";
      }

      answerSection.appendChild(feedbackBox);
    }

    contentBlock.appendChild(answerSection);
    card.appendChild(contentBlock);

    if (fieldsGrid) {
      fieldsGrid.appendChild(card);
    }
  });

  if (fieldsSection) {
    fieldsSection.style.display = "block";
  }
}

// ---------------------------------------------------------------------------
// Profile Autofill Implementation
// ---------------------------------------------------------------------------
async function autofillFromProfile() {
  clearError();
  const currentUser = auth.currentUser;
  if (!currentUser) {
    showError("You must be logged in to autofill from your profile.");
    return;
  }

  if (!lastAnalysisData || !lastAnalysisData.analysis || !lastAnalysisData.analysis.fields) {
    showError("Please analyse the form first before autofilling.");
    return;
  }

  const fields = lastAnalysisData.analysis.fields;

  if (autofillBtn) {
    autofillBtn.disabled = true;
    autofillBtn.textContent = "Reading profile...";
  }

  try {
    const userDocRef = doc(db, "users", currentUser.uid);
    const docSnap = await getDoc(userDocRef);

    if (!docSnap.exists()) {
      showError("No saved Student Profile found. Visit the Student Profile page to set up your details.");
      return;
    }

    const p = docSnap.data() || {};
    const filledFields = [];

    fields.forEach((field) => {
      const fieldId = String(field.field_id || field.field_name);
      const fn = (field.field_name || "").toLowerCase();
      const q = (field.question || "").toLowerCase();

      // SAFETY: Do not overwrite an answer the student has already entered!
      const existing = (studentAnswers[fieldId] || "").trim();
      if (existing) {
        return;
      }

      let matchedValue = null;

      // 1. Full Name (exclude parent / guardian / emergency)
      if (
        (fn.includes("name") || q.includes("name")) &&
        !fn.includes("parent") && !fn.includes("guardian") && !fn.includes("emergency") && !fn.includes("institution")
      ) {
        matchedValue = p.name || currentUser.displayName || "";
      }
      // 2. Email Address
      else if (fn.includes("email") || q.includes("email")) {
        matchedValue = p.email || currentUser.email || "";
      }
      // 3. Mobile / Phone (exclude parent / emergency)
      else if (
        (fn.includes("mobile") || fn.includes("phone") || fn.includes("contact")) &&
        !fn.includes("parent") && !fn.includes("guardian") && !fn.includes("emergency")
      ) {
        matchedValue = p.phone || "";
      }
      // 4. Date of Birth
      else if (fn.includes("birth") || fn.includes("dob") || q.includes("birth") || q.includes("dob")) {
        matchedValue = p.dob || "";
      }
      // 5. Gender
      else if (fn === "gender" || fn === "sex" || q.includes("gender")) {
        matchedValue = p.gender || "";
      }
      // 6. College / Institution
      else if (fn.includes("college") || fn.includes("institution") || fn.includes("school") || q.includes("institution")) {
        matchedValue = p.college || "";
      }
      // 7. Department
      else if (fn.includes("department") || q.includes("department")) {
        matchedValue = p.department || "";
      }
      // 8. Course / Programme
      else if (fn.includes("course") || fn.includes("programme") || q.includes("course")) {
        matchedValue = p.course || "";
      }
      // 9. Year of Study
      else if (fn.includes("year") || q.includes("year")) {
        matchedValue = p.academicYear || "";
      }
      // 10. Address
      else if (fn.includes("address") || q.includes("address")) {
        matchedValue = p.address || "";
      }

      if (matchedValue && String(matchedValue).trim()) {
        const valStr = String(matchedValue).trim();
        studentAnswers[fieldId] = valStr;
        filledFields.push(field.question || field.field_name);

        const inputEl = document.getElementById(`input_${fieldId}`);
        if (inputEl) {
          inputEl.value = valStr;
          inputEl.classList.remove("input-error");
        }
      }
    });

    // Show clear message explaining which fields were filled
    if (autofillBanner && autofillBannerText) {
      if (filledFields.length > 0) {
        autofillBannerText.textContent = `Autofilled ${filledFields.length} field(s) from your profile: ${filledFields.join(", ")}. You can review and edit any value.`;
        autofillBanner.style.display = "flex";
      } else {
        autofillBannerText.textContent = "No matching profile fields found to autofill (or fields already contain answers).";
        autofillBanner.style.display = "flex";
      }
    }

  } catch (err) {
    console.error("Autofill error:", err);
    showError("Could not load your student profile for autofill: " + err.message);
  } finally {
    if (autofillBtn) {
      autofillBtn.disabled = false;
      autofillBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
        Autofill from My Profile
      `;
    }
  }
}

// ---------------------------------------------------------------------------
// Validate Form Answers via POST /api/validate
// ---------------------------------------------------------------------------
async function performValidation() {
  if (isSubmittingValidation) return;

  if (!currentDocId) {
    showError("No document selected for validation. Please upload a document first.");
    return;
  }

  clearError();

  const currentUser = auth.currentUser;
  if (!currentUser) {
    showError("Your session has expired. Redirecting to login...");
    setTimeout(() => window.location.replace("login.html"), 1500);
    return;
  }

  // 1. Sync current answers from inputs into studentAnswers map
  if (lastAnalysisData?.analysis?.fields) {
    lastAnalysisData.analysis.fields.forEach((f) => {
      const fid = String(f.field_id || f.field_name);
      const inputEl = document.getElementById(`input_${fid}`);
      if (inputEl) {
        studentAnswers[fid] = inputEl.value.trim();
      }
    });
  }

  isSubmittingValidation = true;

  // Set loading states on both Validate buttons
  const setValidateButtonsLoading = (loading) => {
    [validateBtnTop, validateBtnBottom].forEach((btn) => {
      if (!btn) return;
      btn.disabled = loading;
      if (loading) {
        btn.innerHTML = `
          <span class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0 6px 0 0; display: inline-block; vertical-align: middle;"></span>
          Validating...
        `;
      } else {
        btn.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          Validate My Answers
        `;
      }
    });
  };

  setValidateButtonsLoading(true);

  try {
    const idToken = await currentUser.getIdToken();
    const selectedLang = languageSelect ? languageSelect.value : "both";

    const response = await fetch(VALIDATE_API_URL, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${idToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: currentDocId,
        answers: studentAnswers,
        language: selectedLang
      })
    });

    const data = await response.json();

    if (response.status === 401) {
      showError("Authentication expired. Please sign in again.");
      setTimeout(() => window.location.replace("login.html"), 1500);
      return;
    }

    if (response.status === 429) {
      showError("Too many validation requests. Please wait a moment before trying again.");
      return;
    }

    if (!response.ok || !data.success) {
      throw new Error(data.error || `Server error during validation (${response.status})`);
    }

    // Store validation results
    overallValidation = data;
    validationResults = {};
    (data.field_results || []).forEach((fr) => {
      validationResults[fr.field_id] = fr;
    });

    // Re-render field cards with validation feedback while preserving student input
    renderAnalysisResults(lastAnalysisData, selectedLang);

    // Smoothly scroll to the validation summary
    if (validationSummaryCard) {
      validationSummaryCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }

  } catch (err) {
    console.error("Validation error:", err);
    showError(err.message || "An unexpected error occurred while validating your answers.");
  } finally {
    isSubmittingValidation = false;
    setValidateButtonsLoading(false);
  }
}

// ---------------------------------------------------------------------------
// AI Form Analysis Flow (Preserved from Phase 5)
// ---------------------------------------------------------------------------
async function performAnalysis() {
  if (!currentDocId) {
    showError("No document selected to analyse. Please upload a document first.");
    return;
  }

  clearError();

  const currentUser = auth.currentUser;
  if (!currentUser) {
    showError("Your session has expired. Redirecting to login...");
    setTimeout(() => window.location.replace("login.html"), 1500);
    return;
  }

  let idToken = "";
  try {
    idToken = await currentUser.getIdToken();
  } catch (err) {
    showError("Could not retrieve authentication credentials. Please sign in again.");
    return;
  }

  const selectedLang = languageSelect ? languageSelect.value : "both";

  // UI loading state
  if (analyseBtn) {
    analyseBtn.disabled = true;
    analyseBtn.innerHTML = `
      <span class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0 6px 0 0; display: inline-block; vertical-align: middle;"></span>
      Analysing...
    `;
  }

  if (loadingCard) loadingCard.style.display = "block";
  if (overviewCard) overviewCard.style.display = "none";
  if (fieldsSection) fieldsSection.style.display = "none";

  loadingCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const response = await fetch(ANALYSE_API_URL, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${idToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: currentDocId,
        language: selectedLang
      })
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || `Server returned error status: ${response.status}`);
    }

    // Reset validation state on re-analysis, but keep existing student answers
    validationResults = null;
    overallValidation = null;

    renderAnalysisResults(data, selectedLang);

  } catch (err) {
    console.error("AI Analysis error:", err);
    showError(err.message || "An unexpected error occurred during form analysis.");
  } finally {
    if (loadingCard) loadingCard.style.display = "none";
    if (analyseBtn) {
      analyseBtn.disabled = false;
      analyseBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"></path>
        </svg>
        Re-Analyse Form
      `;
    }
  }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------
if (analyseBtn) {
  analyseBtn.addEventListener("click", performAnalysis);
}

if (autofillBtn) {
  autofillBtn.addEventListener("click", autofillFromProfile);
}

if (validateBtnTop) {
  validateBtnTop.addEventListener("click", performValidation);
}

if (validateBtnBottom) {
  validateBtnBottom.addEventListener("click", performValidation);
}

function navigateToPreview() {
  if (!currentDocId) {
    showError("Please select a document first.");
    return;
  }
  try {
    sessionStorage.setItem("formwise_preview_answers", JSON.stringify(studentAnswers));
  } catch (e) {
    console.warn("Could not save answers to sessionStorage:", e);
  }
  window.location.href = `preview.html?doc_id=${encodeURIComponent(currentDocId)}`;
}

const previewBtnReadiness = document.getElementById("previewBtnReadiness");
if (previewBtnReadiness) {
  previewBtnReadiness.addEventListener("click", navigateToPreview);
}

const previewBtnBottom = document.getElementById("previewBtnBottom");
if (previewBtnBottom) {
  previewBtnBottom.addEventListener("click", navigateToPreview);
}

// Language switch: re-renders guidance without losing student answers
if (languageSelect) {
  languageSelect.addEventListener("change", () => {
    if (lastAnalysisData) {
      renderAnalysisResults(lastAnalysisData, languageSelect.value);
    }
    if (lastReadinessData) {
      renderReadiness(lastReadinessData);
    }
    if (lastChecklistData) {
      renderChecklist(lastChecklistData);
    }
  });
}

// ---------------------------------------------------------------------------
// Auth Observer & Initialisation
// ---------------------------------------------------------------------------
onAuthStateChanged(auth, (user) => {
  if (user) {
    document.body.classList.add("auth-verified");
    updateHeaderProfile(user);

    currentDocId = getDocIdFromURL();

    if (!currentDocId) {
      if (noDocBanner) noDocBanner.style.display = "flex";
      if (displayDocId) displayDocId.textContent = "None";
      if (analyseBtn) analyseBtn.disabled = true;
    } else {
      if (noDocBanner) noDocBanner.style.display = "none";
      if (displayDocId) displayDocId.textContent = currentDocId;
      if (analyseBtn) analyseBtn.disabled = false;
    }

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

// ===========================================================================
// Phase 7 Step 5 – Document Checklist
// ===========================================================================

/**
 * Fetches /api/checklist and renders the checklist card.
 * SECURITY: Never passes confirmed_matches from the client.
 * The backend ignores any such field; confirmations come from Firestore only.
 */
async function loadChecklist() {
  if (isLoadingChecklist || !currentDocId) return;
  isLoadingChecklist = true;

  const card = getChecklistCard();
  const itemsEl = getChecklistItems();
  const metaEl  = getChecklistMetaRow();

  if (!card || !itemsEl) { isLoadingChecklist = false; return; }

  // Show loading state
  card.style.display = "block";
  while (itemsEl.firstChild) itemsEl.removeChild(itemsEl.firstChild);
  while (metaEl && metaEl.firstChild) metaEl.removeChild(metaEl.firstChild);
  const loadingDiv = createEl("div", "checklist-loading", "");
  const spin = createEl("span", "spinner", "");
  spin.style.cssText = "width:16px;height:16px;border-width:2px;display:inline-block;";
  loadingDiv.appendChild(spin);
  loadingDiv.appendChild(createEl("span", "", "Loading document checklist…"));
  itemsEl.appendChild(loadingDiv);

  try {
    const user = auth.currentUser;
    if (!user) throw new Error("Not authenticated.");
    const token = await user.getIdToken();

    const resp = await fetch(CHECKLIST_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      // SECURITY: document_id only – never send confirmed_matches from the client
      body: JSON.stringify({ document_id: currentDocId })
    });
    const data = await resp.json();
    if (!resp.ok || !data.success) throw new Error(data.error || "Checklist request failed.");

    lastChecklistData = data;
    renderChecklist(data);

  } catch (err) {
    while (itemsEl.firstChild) itemsEl.removeChild(itemsEl.firstChild);
    itemsEl.appendChild(createEl("div", "checklist-empty-state", `Could not load checklist: ${err.message}`));
  } finally {
    isLoadingChecklist = false;
  }
}

/**
 * Renders the checklist card from the backend response.
 * Response fields used:
 *   total_required, mandatory_count, optional_count, matched_count,
 *   missing_mandatory_count, is_complete, items[]
 * Each item: doc_id, title_en, title_ta, is_mandatory, status,
 *            confirmed_doc_id, suggested_doc_id, uploaded_documents[]
 */
function renderChecklist(data) {
  const card    = getChecklistCard();
  const metaEl  = getChecklistMetaRow();
  const itemsEl = getChecklistItems();
  if (!card || !itemsEl) return;

  // Clear existing content safely
  while (metaEl && metaEl.firstChild) metaEl.removeChild(metaEl.firstChild);
  while (itemsEl.firstChild) itemsEl.removeChild(itemsEl.firstChild);

  // Meta badges
  if (metaEl) {
    const addBadge = (text) => {
      const b = createEl("span", "badge-pill", text);
      metaEl.appendChild(b);
    };
    addBadge(`${data.total_required ?? 0} Document${(data.total_required ?? 0) !== 1 ? "s" : ""} Required`);
    addBadge(`${data.matched_count ?? 0} Confirmed`);
    addBadge(`${data.missing_mandatory_count ?? 0} Mandatory Missing`);
  }

  // Empty state
  const items = Array.isArray(data.items) ? data.items : [];
  if (items.length === 0) {
    itemsEl.appendChild(createEl("div", "checklist-empty-state", "✓ No supporting documents required for this form."));
    card.style.display = "block";
    return;
  }

  // Render each document requirement
  items.forEach(item => {
    const wrapper = createEl("div", "checklist-item");

    // Header: title + mandatory/optional badge
    const header = createEl("div", "checklist-item-header");
    const titleBlock = createEl("div", "");
    titleBlock.appendChild(createEl("div", "checklist-item-title", item.title_en || item.doc_id || "Document"));
    if (item.title_ta) {
      titleBlock.appendChild(createEl("div", "checklist-item-title-ta", item.title_ta));
    }
    header.appendChild(titleBlock);
    header.appendChild(createEl(
      "span",
      item.is_mandatory ? "badge-mandatory" : "badge-optional-doc",
      item.is_mandatory ? "Mandatory" : "Optional"
    ));
    wrapper.appendChild(header);

    // Status row
    const statusRow = createEl("div", "doc-status-row");
    // Backend field names: matched_document_id, matched_filename,
    //                      suggested_document_id, suggested_filename
    const matchedDocId = item.matched_document_id || item.confirmed_doc_id;
    if (matchedDocId) {
      const lbl = createEl("span", "status-label-confirmed", "✓ Confirmed: ");
      const id  = createEl("span", "", item.matched_filename || matchedDocId);
      statusRow.appendChild(lbl);
      statusRow.appendChild(id);
    } else if (item.suggested_document_id) {
      const lbl = createEl("span", "status-label-suggested", "⬡ Suggested (not confirmed): ");
      const id  = createEl("span", "", item.suggested_filename || item.suggested_document_id);
      statusRow.appendChild(lbl);
      statusRow.appendChild(id);
    } else {
      statusRow.appendChild(createEl("span", "status-label-missing", "✗ Missing"));
    }
    wrapper.appendChild(statusRow);

    // Action row: select dropdown + Confirm + Clear
    const actionRow = createEl("div", "checklist-action-row");

    const sel = document.createElement("select");
    sel.className = "checklist-select";
    sel.setAttribute("aria-label", `Select document for ${item.title_en || item.doc_id}`);
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— select an uploaded document —";
    sel.appendChild(placeholder);

    // Build the dropdown from the uploaded_documents list in the response.
    const uploads = Array.isArray(data.uploaded_documents) ? data.uploaded_documents : [];
    const extraIds = new Set();
    (data.items || []).forEach(it => {
      const itMatched = it.matched_document_id || it.confirmed_doc_id;
      if (itMatched) extraIds.add(itMatched);
      if (it.suggested_document_id) extraIds.add(it.suggested_document_id);
    });
    const uploadsMap = new Map();
    uploads.forEach(u => {
      const uid = u.document_id || u.id;
      if (uid) uploadsMap.set(uid, u);
    });
    // Add stub entries for any doc IDs not covered by the uploads list
    extraIds.forEach(eid => {
      if (eid && !uploadsMap.has(eid)) {
        uploadsMap.set(eid, { document_id: eid, original_filename: eid });
      }
    });
    const allUploads = Array.from(uploadsMap.values());
    allUploads.forEach(upDoc => {
      const opt = document.createElement("option");
      const upId = upDoc.document_id || upDoc.id || upDoc;
      const upName = upDoc.original_filename || upDoc.filename || upId;
      opt.value = upId;
      opt.textContent = `${upName} (${String(upId).slice(0, 8)}…)`;
      // Pre-select the currently confirmed doc if any
      if (matchedDocId && upId === matchedDocId) opt.selected = true;
      sel.appendChild(opt);
    });

    const confirmBtn = createEl("button", "btn-confirm-doc", "Confirm");
    confirmBtn.type = "button";
    confirmBtn.addEventListener("click", async () => {
      const selectedId = sel.value;
      if (!selectedId) {
        showError("Please select a document from the list before confirming.");
        return;
      }
      await submitChecklistConfirmation(item.doc_id, selectedId, confirmBtn, clearBtn);
    });

    const clearBtn = createEl("button", "btn-clear-doc", "Clear");
    clearBtn.type = "button";
    // Only show Clear if something is currently confirmed
    if (!matchedDocId) clearBtn.style.display = "none";
    clearBtn.addEventListener("click", async () => {
      await submitChecklistConfirmation(item.doc_id, null, confirmBtn, clearBtn);
    });

    actionRow.appendChild(sel);
    actionRow.appendChild(confirmBtn);
    actionRow.appendChild(clearBtn);
    wrapper.appendChild(actionRow);

    itemsEl.appendChild(wrapper);
  });

  card.style.display = "block";
}

/**
 * Sends a confirmation (or clear) to /api/checklist/confirm, then refreshes both
 * the checklist and the readiness score without reloading the page.
 */
async function submitChecklistConfirmation(requirementId, selectedDocId, confirmBtn, clearBtn) {
  if (isSubmittingConfirmation) return;
  isSubmittingConfirmation = true;
  if (confirmBtn) confirmBtn.disabled = true;
  if (clearBtn)   clearBtn.disabled   = true;

  try {
    const user = auth.currentUser;
    if (!user) throw new Error("Not authenticated.");
    const token = await user.getIdToken();

    const payload = {
      document_id:    currentDocId,
      requirement_id: requirementId,
      selected_doc_id: selectedDocId   // null = clear the confirmation
    };

    const resp = await fetch(CHECKLIST_CONFIRM_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (!resp.ok || !data.success) throw new Error(data.error || "Confirmation failed.");

    // Refresh checklist and readiness in-place (no page reload)
    await loadChecklist();
    await loadReadiness();

  } catch (err) {
    showError(`Document confirmation error: ${err.message}`);
    if (confirmBtn) confirmBtn.disabled = false;
    if (clearBtn)   clearBtn.disabled   = false;
  } finally {
    isSubmittingConfirmation = false;
  }
}

// ===========================================================================
// Phase 7 Step 5 – Application Readiness Score
// ===========================================================================

/**
 * Fetches /api/readiness and renders the readiness card.
 * Uses the current studentAnswers map so the score reflects typed answers.
 * SECURITY: confirmed_matches come from Firestore (backend), not this client.
 */
async function loadReadiness() {
  if (isLoadingReadiness || !currentDocId) return;
  isLoadingReadiness = true;

  const card = getReadinessCard();
  if (!card) { isLoadingReadiness = false; return; }

  try {
    const user = auth.currentUser;
    if (!user) throw new Error("Not authenticated.");
    const token = await user.getIdToken();

    // Send current student answers so readiness reflects their input
    const resp = await fetch(READINESS_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        document_id: currentDocId,
        answers: studentAnswers   // current in-memory answers (may be empty before validation)
      })
    });
    const data = await resp.json();
    if (!resp.ok || !data.success) throw new Error(data.error || "Readiness request failed.");

    lastReadinessData = data;
    renderReadiness(data);

  } catch (err) {
    card.style.display = "block";
    const scoreEl = getReadinessScore();
    if (scoreEl) scoreEl.textContent = "–";
    const statusEl = getReadinessStatus();
    if (statusEl) statusEl.textContent = `Could not load: ${err.message}`;
  } finally {
    isLoadingReadiness = false;
  }
}

/**
 * Renders the readiness card from the backend response.
 * Response fields used:
 *   readiness_score, status, score_breakdown{}, action_items[],
 *   validation_summary{}, checklist_summary{}
 */
function renderReadiness(data) {
  const card      = getReadinessCard();
  const scoreEl   = getReadinessScore();
  const statusEl  = getReadinessStatus();
  const bkdEl     = getReadinessBreakdown();
  const actionsEl = getReadinessActions();
  if (!card || !data) return;

  // 1. Total Score (0-100)
  const score = typeof data.readiness_score === "number"
    ? Math.round(data.readiness_score)
    : 0;
  if (scoreEl) scoreEl.textContent = String(score);

  // 2. Status pill with robust mapping for backend & frontend keys
  if (statusEl) {
    const rawStatus = data.status || "not_started";
    const statusLabels = {
      ready_to_submit: "✓ Ready to Submit",
      almost_ready:    "Almost Ready",
      in_progress:     "In Progress",
      not_started:     "Not Started",
      complete:        "✓ Ready to Submit",
      mostly_ready:    "Almost Ready",
      partially_ready: "In Progress"
    };
    const statusClassMap = {
      ready_to_submit: "complete",
      almost_ready:    "mostly_ready",
      in_progress:     "partially_ready",
      not_started:     "not_started",
      complete:        "complete",
      mostly_ready:    "mostly_ready",
      partially_ready: "partially_ready"
    };
    statusEl.textContent = statusLabels[rawStatus] || rawStatus;
    statusEl.className = `readiness-status-pill ${statusClassMap[rawStatus] || rawStatus}`;
  }

  // 3. Score breakdown grid using exact backend property names and justified calculations
  if (bkdEl) {
    while (bkdEl.firstChild) bkdEl.removeChild(bkdEl.firstChild);
    const bd = data.score_breakdown || {};

    const fieldsScore = bd.fields_score ?? bd.field_score ?? 0;
    const fieldsMax   = bd.fields_max ?? 60;
    const docsScore   = bd.documents_score ?? bd.document_score ?? 0;
    const docsMax     = bd.documents_max ?? 40;

    const totalReq = bd.total_required_fields ?? 0;
    const compReq  = bd.completed_required_fields ?? 0;
    const totalOpt = bd.total_optional_fields ?? 0;
    const compOpt  = bd.completed_optional_fields ?? 0;

    // Calculate mathematically justified points if not directly provided
    let reqPts = bd.required_points;
    let optPts = bd.optional_points;
    let reqMax = 50;
    let optMax = 10;

    if (totalReq > 0 && totalOpt > 0) {
      reqMax = 50;
      optMax = 10;
      if (reqPts === undefined) reqPts = Math.round(((compReq / totalReq) * 50) * 100) / 100;
      if (optPts === undefined) optPts = Math.round(((compOpt / totalOpt) * 10) * 100) / 100;
    } else if (totalReq > 0 && totalOpt === 0) {
      reqMax = 60;
      optMax = 0;
      if (reqPts === undefined) reqPts = Math.round(((compReq / totalReq) * 60) * 100) / 100;
      if (optPts === undefined) optPts = 0;
    } else if (totalReq === 0 && totalOpt > 0) {
      reqMax = 0;
      optMax = 60;
      if (reqPts === undefined) reqPts = 0;
      if (optPts === undefined) optPts = Math.round(((compOpt / totalOpt) * 60) * 100) / 100;
    } else {
      reqMax = 0;
      optMax = 0;
      if (reqPts === undefined) reqPts = 0;
      if (optPts === undefined) optPts = 0;
    }

    const cells = [
      {
        label: "Field Score",
        value: `${fieldsScore} / ${fieldsMax}`,
        title: `Field completion & validity score: ${fieldsScore} out of ${fieldsMax} max points`
      },
      {
        label: "Required Fields",
        value: `${compReq} / ${totalReq} (${reqPts} pts)`,
        title: `${compReq} of ${totalReq} required fields completed (${reqPts} / ${reqMax} points)`
      },
      {
        label: "Optional Fields",
        value: `${compOpt} / ${totalOpt} (${optPts} pts)`,
        title: `${compOpt} of ${totalOpt} optional fields completed (${optPts} / ${optMax} bonus points)`
      },
      {
        label: "Document Score",
        value: `${docsScore} / ${docsMax}`,
        title: `Supporting documents score: ${docsScore} out of ${docsMax} max points`
      }
    ];

    cells.forEach(c => {
      const cell = createEl("div", "readiness-breakdown-cell");
      if (c.title) cell.setAttribute("title", c.title);
      cell.appendChild(createEl("div", "cell-val", String(c.value)));
      cell.appendChild(createEl("div", "cell-lbl", c.label));
      bkdEl.appendChild(cell);
    });
  }

  // 4. Action items (Safe DOM extraction – no [object Object] and strictly textContent)
  if (actionsEl) {
    while (actionsEl.firstChild) actionsEl.removeChild(actionsEl.firstChild);
    const items = Array.isArray(data.action_items) ? data.action_items : [];
    if (items.length > 0) {
      actionsEl.appendChild(createEl("div", "readiness-actions-title", "What to do next:"));
      const ul = document.createElement("ul");
      ul.className = "readiness-actions-list";

      const selectedLang = languageSelect ? languageSelect.value : "both";

      items.forEach(ai => {
        const li = document.createElement("li");

        let msgEn = "";
        let msgTa = "";

        if (typeof ai === "string") {
          msgEn = ai.trim();
        } else if (ai && typeof ai === "object") {
          msgEn = String(ai.message_en || ai.message || ai.suggestion_en || ai.label || ai.title || "").trim();
          msgTa = String(ai.message_ta || ai.suggestion_ta || ai.title_ta || "").trim();
        }

        if (selectedLang === "tamil" && msgTa) {
          li.textContent = msgTa;
        } else if (selectedLang === "both" && msgEn && msgTa && msgEn !== msgTa) {
          const enDiv = createEl("div", "", msgEn);
          const taDiv = createEl("div", "readiness-action-ta", msgTa);
          taDiv.style.cssText = "font-size: 0.85rem; color: #4B5563; margin-top: 2px;";
          li.appendChild(enDiv);
          li.appendChild(taDiv);
        } else {
          li.textContent = msgEn || msgTa || "Action item pending review.";
        }

        ul.appendChild(li);
      });
      actionsEl.appendChild(ul);
    } else {
      actionsEl.appendChild(createEl("div", "readiness-no-actions", "✓ No outstanding action items. Your application looks complete!"));
    }
  }

  card.style.display = "block";
}

// ===========================================================================
// Hook checklist + readiness into the existing analysis flow
// ===========================================================================

// After AI analysis completes, automatically load the checklist and readiness
const _origRenderAnalysisResults = renderAnalysisResults;
// We patch the auth observer to also load checklist/readiness once a doc is set.
// The existing onAuthStateChanged already initialises currentDocId.
// We trigger checklist+readiness after a successful analysis.
const _origPerformAnalysis = performAnalysis;

// Override performAnalysis to also load checklist + readiness afterwards
window.__fw_performAnalysis_wrapped = async function () {
  await _origPerformAnalysis();
  // Load checklist and readiness after every (re-)analysis
  if (currentDocId) {
    await loadChecklist();
    await loadReadiness();
  }
};
// Replace the analyseBtn listener with the wrapped version
if (analyseBtn) {
  analyseBtn.removeEventListener("click", performAnalysis);
  analyseBtn.addEventListener("click", window.__fw_performAnalysis_wrapped);
}

// Also refresh readiness after validation, so the score reflects updated answers
const _origPerformValidation = performValidation;
window.__fw_performValidation_wrapped = async function () {
  await _origPerformValidation();
  if (currentDocId) await loadReadiness();
};
if (validateBtnTop) {
  validateBtnTop.removeEventListener("click", performValidation);
  validateBtnTop.addEventListener("click", window.__fw_performValidation_wrapped);
}
if (validateBtnBottom) {
  validateBtnBottom.removeEventListener("click", performValidation);
  validateBtnBottom.addEventListener("click", window.__fw_performValidation_wrapped);
}
