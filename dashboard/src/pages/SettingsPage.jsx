/**
 * Page: SettingsPage — Application settings (theme, audio, account).
 */

import ThemeToggle from '@/components/layout/ThemeToggle';

export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Appearance</h2>
        <div className="flex items-center justify-between rounded-lg border border-border p-4">
          <span>Theme</span>
          <ThemeToggle />
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Audio</h2>
        <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
          {/* Microphone selection, speaker selection, noise suppression toggle */}
          Audio settings coming soon
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Account</h2>
        <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
          {/* User info, sign out, delete account */}
          Account settings coming soon
        </div>
      </section>
    </div>
  );
}
