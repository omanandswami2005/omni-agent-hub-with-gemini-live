/**
 * useAuth — Firebase auth state listener.
 */

// TODO: Implement auth hook:
//   - onAuthStateChanged listener
//   - getIdToken() for WS auth
//   - signInWithPopup (Google)
//   - signOut

export function useAuth() {
  return { user: null, token: null, loading: true, signIn: () => {}, signOut: () => {} };
}
