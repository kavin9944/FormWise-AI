import { initializeApp } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-firestore.js";

// Firebase configuration for FormWise AI
const firebaseConfig = {
  apiKey: "AIzaSyCuM6ZmnblJIQfX5mb5wnJXuJAfNtQxXmg",
  authDomain: "formwise-ai-7caa9.firebaseapp.com",
  databaseURL: "https://formwise-ai-7caa9-default-rtdb.firebaseio.com",
  projectId: "formwise-ai-7caa9",
  storageBucket: "formwise-ai-7caa9.firebasestorage.app",
  messagingSenderId: "838114932351",
  appId: "1:838114932351:web:24e15960978659793c314a",
  measurementId: "G-6HVYTY0RVN"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firebase services
export const auth = getAuth(app);
export const db = getFirestore(app);

console.log("Firebase connected successfully!");
