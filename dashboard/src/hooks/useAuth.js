/**
 * useAuth — Firebase auth state listener with auto-token-refresh.
 */

import { useEffect } from 'react';
import { onAuthStateChanged, signInWithPopup, signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut as fbSignOut } from 'firebase/auth';
import { auth, googleProvider } from '@/lib/firebase';
import { useAuthStore } from '@/stores/authStore';

export function useAuth() {
  const { user, token, loading, setUser, logout, setLoading } = useAuthStore();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (fbUser) => {
      if (fbUser) {
        const idToken = await fbUser.getIdToken();
        setUser(
          {
            uid: fbUser.uid,
            email: fbUser.email,
            displayName: fbUser.displayName,
            photoURL: fbUser.photoURL,
          },
          idToken,
        );
      } else {
        logout();
      }
    });
    return unsubscribe;
  }, [setUser, logout, setLoading]);

  // Refresh token every 50 minutes (tokens expire at 60)
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(async () => {
      const fbUser = auth.currentUser;
      if (fbUser) {
        const idToken = await fbUser.getIdToken(true);
        setUser(
          {
            uid: fbUser.uid,
            email: fbUser.email,
            displayName: fbUser.displayName,
            photoURL: fbUser.photoURL,
          },
          idToken,
        );
      }
    }, 50 * 60 * 1000);
    return () => clearInterval(interval);
  }, [user, setUser]);

  const signIn = () => signInWithPopup(auth, googleProvider);
  const signInWithEmail = (email, password) => signInWithEmailAndPassword(auth, email, password);
  const signUpWithEmail = (email, password) => createUserWithEmailAndPassword(auth, email, password);
  const signOut = async () => {
    try {
      await fbSignOut(auth);
    } catch (error) {
      console.error('Sign out error:', error);
    } finally {
      // Clear all Firebase auth data from localStorage and sessionStorage
      try {
        for (const key in localStorage) {
          if (key.startsWith('firebase:')) {
            localStorage.removeItem(key);
          }
        }
        for (const key in sessionStorage) {
          if (key.startsWith('firebase:')) {
            sessionStorage.removeItem(key);
          }
        }
      } catch (e) {
        console.error('Error clearing storage:', e);
      }
      // Clear user state
      logout();
    }
  };

  return { user, token, loading, signIn, signInWithEmail, signUpWithEmail, signOut };
}
