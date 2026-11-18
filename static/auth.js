// Connexion Firebase : le jeton est copié dans le cookie __session, envoyé avec chaque requête au serveur.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  createUserWithEmailAndPassword, getAuth, GoogleAuthProvider, onIdTokenChanged,
  signInWithEmailAndPassword, signInWithPopup, signOut,
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

const auth = getAuth(initializeApp({
  apiKey: "AIzaSyCbMnwylcQKSErsQ5kcpmtCeZFLgl055yc",
  authDomain: "helper-job-search-center.firebaseapp.com",
  projectId: "helper-job-search-center",
  appId: "1:263454823776:web:e81bf0ce1d2760a31fba05",
}));

window.authApi = {
  signIn: (email, password) => signInWithEmailAndPassword(auth, email, password),
  signUp: (email, password) => createUserWithEmailAndPassword(auth, email, password),
  google: () => signInWithPopup(auth, new GoogleAuthProvider()),
  signOut: () => signOut(auth),
};

onIdTokenChanged(auth, async (user) => {
  const token = user ? await user.getIdToken() : "";
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `__session=${token}; path=/; SameSite=Strict${secure}${user ? "" : "; max-age=0"}`;
  onAuth(user);
});
