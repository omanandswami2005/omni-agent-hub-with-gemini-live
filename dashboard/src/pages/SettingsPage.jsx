/**
 * Page: SettingsPage — Application settings (theme, audio, privacy, shortcuts).
 */

import { useState } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import ThemeToggle from '@/components/layout/ThemeToggle';
import { useAuthStore } from '@/stores/authStore';
import { useAuth } from '@/hooks/useAuth';

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
  const user = useAuthStore((s) => s.user);
  const { signOut } = useAuth();

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
                  <button onClick={signOut} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted">
                    Sign out
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
