/**
 * Auth: AuthGuard — Route guard that redirects unauthenticated users to login.
 */

// TODO: Implement with useAuth hook + Navigate redirect

export default function AuthGuard({ children }) {
  // const { user, loading } = useAuth();
  // if (loading) return <LoadingSpinner />;
  // if (!user) return <Navigate to="/login" />;
  return children;
}
