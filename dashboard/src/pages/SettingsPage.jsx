/**
 * Page: SettingsPage — Application settings (theme, audio, privacy, shortcuts).
 */

import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { toast } from 'sonner';
import ThemeToggle from '@/components/layout/ThemeToggle';
import { useAuthStore } from '@/stores/authStore';
import { useAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { auth } from '@/lib/firebase';
import { useVoice } from '@/hooks/useVoiceProvider';

const TABS = ['General', 'Audio', 'Privacy', 'Shortcuts'];

const SHORTCUTS = [
  { keys: 'Ctrl + K', action: 'Command palette' },
  { keys: 'Ctrl + /', action: 'Toggle sidebar' },
  { keys: 'Space', action: 'Push-to-talk (when not in input)' },
  { keys: 'Escape', action: 'Stop recording / close modal' },
];

export default function SettingsPage() {
  useDocumentTitle('Settings');
  const [tab, setTab] = useState('General');
  const [signingOut, setSigningOut] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const user = useAuthStore((s) => s.user);
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const voice = useVoice();

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOut();
      // Wait a bit for the auth state to propagate
      await new Promise(resolve => setTimeout(resolve, 500));
      // Force a full page reload with cache bypass to clear all state
      window.location.replace('/login?t=' + Date.now());
    } catch (error) {
      console.error('Sign out failed:', error);
      // Force navigation even if signOut fails
      window.location.replace('/login?t=' + Date.now());
    } finally {
      setSigningOut(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirmText !== 'DELETE') return;
    setDeleting(true);
    try {
      // Re-authenticate to get a fresh token (Firebase requires recent auth for destructive ops)
      const fbUser = auth.currentUser;
      if (fbUser) {
        const freshToken = await fbUser.getIdToken(true);
        await api.delete('/auth/account', { token: freshToken });
      }
      toast.success('Account deleted successfully');
      await signOut();
      window.location.replace('/login?t=' + Date.now());
    } catch (error) {
      console.error('Account deletion failed:', error);
      toast.error(error.message || 'Failed to delete account. Please try again.');
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
      setDeleteConfirmText('');
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Tab nav */}
      <nav className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${tab === t ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            {t}
          </button>
        ))}
      </nav>

      {/* General */}
      {tab === 'General' && (
        <div className="space-y-6">
          <section className="space-y-4">
            <h2 className="text-lg font-medium">Appearance</h2>
            <div className="flex items-center justify-between rounded-lg border border-border p-4">
              <span>Theme</span>
              <ThemeToggle />
            </div>
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-medium">Account</h2>
            <div className="rounded-lg border border-border p-4">
              {user ? (
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{user.displayName || user.email}</p>
                    <p className="text-sm text-muted-foreground">{user.email}</p>
                  </div>
                  <button onClick={handleSignOut} disabled={signingOut} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50">
                    {signingOut ? 'Signing out...' : 'Sign out'}
                  </button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Not signed in</p>
              )}
            </div>
          </section>
        </div>
      )}

      {/* Audio */}
      {tab === 'Audio' && (
        <div className="space-y-4">
          <h2 className="text-lg font-medium">Audio Settings</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border border-border p-4">
              <div>
                <p className="text-sm font-medium">Voice output</p>
                <p className="text-xs text-muted-foreground">
                  When enabled, the AI responds with voice. When disabled, only text responses are shown.
                </p>
              </div>
              <button
                onClick={() => voice.toggleVoice?.()}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors ${voice.voiceEnabled ? 'bg-primary' : 'bg-muted'}`}
              >
                <span className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${voice.voiceEnabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border p-4">
              <span className="text-sm">Input sample rate</span>
              <span className="text-sm text-muted-foreground">16 kHz (PCM16)</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border p-4">
              <span className="text-sm">Output sample rate</span>
              <span className="text-sm text-muted-foreground">24 kHz (PCM16)</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border p-4">
              <span className="text-sm">Audio capture</span>
              <span className="text-sm text-muted-foreground">AudioWorklet</span>
            </div>
          </div>
        </div>
      )}

      {/* Privacy */}
      {tab === 'Privacy' && (
        <div className="space-y-6">
          <div className="space-y-4">
            <h2 className="text-lg font-medium">Privacy</h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border border-border p-4">
                <div>
                  <p className="text-sm font-medium">Data retention</p>
                  <p className="text-xs text-muted-foreground">Store conversation history in Firestore</p>
                </div>
                <span className="text-sm text-muted-foreground">Enabled</span>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border p-4">
                <div>
                  <p className="text-sm font-medium">Analytics</p>
                  <p className="text-xs text-muted-foreground">Help improve Omni with usage analytics</p>
                </div>
                <span className="text-sm text-muted-foreground">Disabled</span>
              </div>
            </div>
          </div>

          {/* Danger Zone */}
          <section className="space-y-4">
            <h2 className="text-lg font-medium text-destructive">Danger Zone</h2>
            <div className="rounded-lg border-2 border-destructive/30 p-4 space-y-4">
              <div>
                <p className="text-sm font-medium">Delete Account</p>
                <p className="text-xs text-muted-foreground">
                  Permanently delete your account and all associated data including sessions, personas, memories, and AI data. This action cannot be undone.
                </p>
              </div>

              {!showDeleteConfirm ? (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
                >
                  Delete my account
                </button>
              ) : (
                <div className="space-y-3 rounded-lg bg-destructive/5 p-4">
                  <p className="text-sm font-medium text-destructive">
                    Are you absolutely sure? This will permanently delete:
                  </p>
                  <ul className="text-xs text-muted-foreground space-y-1 list-disc pl-4">
                    <li>All conversation sessions and chat history</li>
                    <li>All custom personas you created</li>
                    <li>All stored memories and AI-learned facts</li>
                    <li>Your Vertex AI data and agent engine sessions</li>
                    <li>Your Firebase authentication account</li>
                  </ul>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">
                      Type <span className="font-mono font-bold text-destructive">DELETE</span> to confirm
                    </label>
                    <input
                      type="text"
                      value={deleteConfirmText}
                      onChange={(e) => setDeleteConfirmText(e.target.value)}
                      placeholder="DELETE"
                      className="w-48 rounded-md border border-destructive/50 bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-destructive"
                      autoComplete="off"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleDeleteAccount}
                      disabled={deleteConfirmText !== 'DELETE' || deleting}
                      className="rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {deleting ? 'Deleting...' : 'Permanently delete my account'}
                    </button>
                    <button
                      onClick={() => {
                        setShowDeleteConfirm(false);
                        setDeleteConfirmText('');
                      }}
                      className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {/* Shortcuts */}
      {tab === 'Shortcuts' && (
        <div className="space-y-4">
          <h2 className="text-lg font-medium">Keyboard Shortcuts</h2>
          <div className="rounded-lg border border-border">
            {SHORTCUTS.map((s, i) => (
              <div key={i} className={`flex items-center justify-between p-4 ${i > 0 ? 'border-t border-border' : ''}`}>
                <span className="text-sm">{s.action}</span>
                <kbd className="rounded bg-muted px-2 py-1 font-mono text-xs">{s.keys}</kbd>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
