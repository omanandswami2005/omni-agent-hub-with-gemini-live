import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useThemeStore = create(
  persist(
    (set) => ({
      theme: 'dark', // 'dark' | 'light' | 'system'
      setTheme: (theme) => {
        const root = document.documentElement;
        root.classList.toggle('dark', theme === 'dark');
        root.classList.toggle('light', theme === 'light');
        set({ theme });
      },
    }),
    { name: 'omni-theme' },
  ),
);
