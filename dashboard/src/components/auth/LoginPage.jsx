/**
 * Auth: LoginPage — Firebase Google sign-in page.
 */

// TODO: Implement:
//   - Google sign-in button
//   - App branding/logo
//   - Loading state during auth

export default function LoginPage({ onLogin }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 rounded-lg border border-border p-8 text-center">
        <h1 className="text-3xl font-bold">Omni</h1>
        <p className="text-muted-foreground">Speak anywhere. Act everywhere.</p>
        <button
          onClick={onLogin}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-border px-4 py-3 text-sm font-medium hover:bg-muted"
        >
          Sign in with Google
        </button>
      </div>
    </div>
  );
}
