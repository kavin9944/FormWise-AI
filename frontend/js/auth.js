import { auth, db } from "./firebase.js";

import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut
} from "https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js";

import {
  doc,
  setDoc
} from "https://www.gstatic.com/firebasejs/13.3.0/firebase-firestore.js";

// REGISTER NEW USER
export async function registerUser(name, email, password) {
  try {
    const userCredential = await createUserWithEmailAndPassword(
      auth,
      email,
      password
    );

    const user = userCredential.user;

    await setDoc(doc(db, "users", user.uid), {
      name: name,
      email: email,
      createdAt: new Date()
    });

    return { success: true, user };
  } catch (error) {
    return { success: false, message: error.message };
  }
}

// LOGIN USER
export async function loginUser(email, password) {
  try {
    const userCredential = await signInWithEmailAndPassword(
      auth,
      email,
      password
    );

    return { success: true, user: userCredential.user };
  } catch (error) {
    return { success: false, message: error.message };
  }
}

// LOGOUT USER
export async function logoutUser() {
  try {
    await signOut(auth);
    return { success: true };
  } catch (error) {
    return { success: false, message: error.message };
  }
}


const loginForm = document.getElementById("loginForm");

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = loginForm.querySelector('input[type="email"]').value.trim();
    const password = loginForm.querySelector('input[type="password"]').value;

    const result = await loginUser(email, password);

    if (result.success) {
      alert("Login successful!");
      window.location.href = "dashboard.html";
    } else {
      alert("Login failed: " + result.message);
    }
  });
}
