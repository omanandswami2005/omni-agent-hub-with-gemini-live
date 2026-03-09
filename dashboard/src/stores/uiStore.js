import { create } from 'zustand';

export const useUiStore = create((set) => ({
  sidebarOpen: true,
  commandPaletteOpen: false,
  activeModal: null,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setCommandPalette: (open) => set({ commandPaletteOpen: open }),
  setActiveModal: (modal) => set({ activeModal: modal }),
}));
