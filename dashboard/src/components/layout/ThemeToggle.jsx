/**
 * Layout: ThemeToggle — Dark/Light/System theme switcher.
 */

import { useThemeStore } from '@/stores/themeStore';

export default function ThemeToggle() {
  const { theme, setTheme } = useThemeStore();

  return (
    <button
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      className="rounded-md p-2 hover:bg-muted"
      aria-label="Toggle theme"
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  );
}
