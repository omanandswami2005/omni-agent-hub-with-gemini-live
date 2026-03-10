/**
 * useAuth — Firebase auth state listener with auto-token-refresh.
 */

import { useEffect } from 'react';
import { onAuthStateChanged, signInWithPopup, signOut as fbSignOut } from 'firebase/auth';
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
  const signOut = () => fbSignOut(auth);

  return { user, token, loading, signIn, signOut };
}
