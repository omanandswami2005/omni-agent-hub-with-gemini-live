/**
 * useFirestore — Firestore real-time subscription helpers.
 */

// TODO: Implement Firestore hooks:
//   - onSnapshot for collections (personas, sessions, mcp_servers)
//   - CRUD wrappers (addDoc, updateDoc, deleteDoc)
//   - Optimistic updates via Zustand store sync

export function useFirestore(collection) {
  return { data: [], loading: true, error: null };
}
