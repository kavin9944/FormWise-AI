/**
 * FormWise AI - Student Profile Service
 * Manages fetching, editing, and saving student profile records in Cloud Firestore.
 */

// 1. Import shared Firebase instances (no duplicate initialization)
import { auth, db } from "./firebase.js";

// 2. Import Auth & Firestore functions
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js";
import {
  doc,
  getDoc,
  setDoc
} from "https://www.gstatic.com/firebasejs/13.3.0/firebase-firestore.js";

import { logoutUser } from "./auth.js";

// UI Element References
const profileForm = document.getElementById("profileForm");
const loadingBanner = document.getElementById("loadingBanner");
const successBanner = document.getElementById("successBanner");
const errorBanner = document.getElementById("errorBanner");
const successText = document.getElementById("successText");
const errorText = document.getElementById("errorText");
const saveProfileBtn = document.getElementById("saveProfileBtn");
const logoutBtn = document.getElementById("logoutBtn");
const headerDisplayName = document.getElementById("headerDisplayName");
const headerAvatar = document.getElementById("headerAvatar");

// Form Field Elements
const fields = {
  name: document.getElementById("name"),
  email: document.getElementById("email"),
  phone: document.getElementById("phone"),
  dob: document.getElementById("dob"),
  gender: document.getElementById("gender"),
  college: document.getElementById("college"),
  department: document.getElementById("department"),
  course: document.getElementById("course"),
  academicYear: document.getElementById("academicYear"),
  address: document.getElementById("address"),
  city: document.getElementById("city"),
  state: document.getElementById("state"),
  pincode: document.getElementById("pincode")
};

let currentUser = null;

/**
 * Display an error message to the user.
 */
function showError(message) {
  if (errorText) errorText.textContent = message;
  if (errorBanner) errorBanner.style.display = "flex";
  if (successBanner) successBanner.style.display = "none";
}

/**
 * Display a success message to the user.
 */
function showSuccess(message) {
  if (successText) successText.textContent = message;
  if (successBanner) successBanner.style.display = "flex";
  if (errorBanner) errorBanner.style.display = "none";

  // Auto-hide success message after 5 seconds
  setTimeout(() => {
    if (successBanner) successBanner.style.display = "none";
  }, 5000);
}

/**
 * Clear all status notification banners.
 */
function clearBanners() {
  if (errorBanner) errorBanner.style.display = "none";
  if (successBanner) successBanner.style.display = "none";
}

/**
 * Update the header avatar and greeting.
 */
function updateHeaderProfile(displayName) {
  const nameToDisplay = displayName || "Student";
  if (headerDisplayName) headerDisplayName.textContent = nameToDisplay;
  if (headerAvatar) headerAvatar.textContent = nameToDisplay.charAt(0).toUpperCase();
}

/**
 * Load student profile from Cloud Firestore users/{uid}.
 */
async function loadStudentProfile(uid) {
  if (loadingBanner) loadingBanner.style.display = "flex";
  clearBanners();

  try {
    const userDocRef = doc(db, "users", uid);
    const docSnap = await getDoc(userDocRef);

    if (docSnap.exists()) {
      const data = docSnap.data();

      // Populate form fields with existing Firestore values (leaving missing fields empty)
      if (fields.name) fields.name.value = data.name || currentUser.displayName || "";
      if (fields.phone) fields.phone.value = data.phone || "";
      if (fields.dob) fields.dob.value = data.dob || "";
      if (fields.gender) fields.gender.value = data.gender || "";
      if (fields.college) fields.college.value = data.college || "";
      if (fields.department) fields.department.value = data.department || "";
      if (fields.course) fields.course.value = data.course || "";
      if (fields.academicYear) fields.academicYear.value = data.academicYear || "";
      if (fields.address) fields.address.value = data.address || "";
      if (fields.city) fields.city.value = data.city || "";
      if (fields.state) fields.state.value = data.state || "";
      if (fields.pincode) fields.pincode.value = data.pincode || "";

      updateHeaderProfile(data.name || currentUser.displayName);
    } else {
      // First-time document creation if profile doesn't exist yet
      if (fields.name) fields.name.value = currentUser.displayName || "";
      updateHeaderProfile(currentUser.displayName);
    }
  } catch (error) {
    console.error("Error loading profile from Firestore:", error);
    showError("Could not load your saved profile data: " + error.message);
  } finally {
    if (loadingBanner) loadingBanner.style.display = "none";
  }
}

/**
 * Save updated student profile to Cloud Firestore users/{uid} with merge: true.
 */
async function saveStudentProfile(event) {
  event.preventDefault();
  if (!currentUser) {
    showError("You must be logged in to save your profile.");
    return;
  }

  clearBanners();

  // Validate required field
  const nameValue = fields.name ? fields.name.value.trim() : "";
  if (!nameValue) {
    showError("Full Name is a required field.");
    if (fields.name) fields.name.focus();
    return;
  }

  // Gather values from form fields
  const updatedProfile = {
    name: nameValue,
    email: currentUser.email, // Kept aligned with Auth email
    phone: fields.phone ? fields.phone.value.trim() : "",
    dob: fields.dob ? fields.dob.value : "",
    gender: fields.gender ? fields.gender.value : "",
    college: fields.college ? fields.college.value.trim() : "",
    department: fields.department ? fields.department.value.trim() : "",
    course: fields.course ? fields.course.value.trim() : "",
    academicYear: fields.academicYear ? fields.academicYear.value : "",
    address: fields.address ? fields.address.value.trim() : "",
    city: fields.city ? fields.city.value.trim() : "",
    state: fields.state ? fields.state.value.trim() : "",
    pincode: fields.pincode ? fields.pincode.value.trim() : "",
    updatedAt: new Date()
  };

  // Set button to saving state
  if (saveProfileBtn) {
    saveProfileBtn.disabled = true;
    saveProfileBtn.innerHTML = `
      <div class="spinner" style="width:16px;height:16px;border-width:2px;border-top-color:#fff;"></div>
      Saving...
    `;
  }

  try {
    const userDocRef = doc(db, "users", currentUser.uid);

    // Save with merge: true to avoid overwriting existing fields such as createdAt
    await setDoc(userDocRef, updatedProfile, { merge: true });

    showSuccess("Your student profile has been saved successfully!");
    updateHeaderProfile(updatedProfile.name);
  } catch (error) {
    console.error("Error saving profile to Firestore:", error);
    showError("Failed to save profile: " + error.message);
  } finally {
    if (saveProfileBtn) {
      saveProfileBtn.disabled = false;
      saveProfileBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
          <polyline points="17 21 17 13 7 13 7 21"></polyline>
          <polyline points="7 3 7 8 15 8"></polyline>
        </svg>
        Save Profile
      `;
    }
  }
}

// ============================================================================
// Authentication Protection & Initialization
// ============================================================================
onAuthStateChanged(auth, async (user) => {
  if (user) {
    currentUser = user;

    // Reveal page once user identity is verified
    document.body.classList.add("auth-verified");

    // Populate read-only email directly from Firebase Auth
    if (fields.email) {
      fields.email.value = user.email || "";
    }

    // Load data from Firestore
    await loadStudentProfile(user.uid);
  } else {
    // Unauthenticated user: redirect immediately to login.html
    window.location.replace("login.html");
  }
});

// Event Listeners
if (profileForm) {
  profileForm.addEventListener("submit", saveStudentProfile);
}

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
