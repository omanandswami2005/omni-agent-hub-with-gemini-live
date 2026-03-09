/**
 * useKeyboard — Global keyboard shortcut handler.
 */

import { useEffect } from 'react';

// TODO: Implement shortcuts:
//   - Ctrl+K → command palette
//   - Ctrl+/ → toggle sidebar
//   - Space (held) → push-to-talk
//   - Escape → close modals

export function useKeyboard(shortcuts = {}) {
  useEffect(() => {
    const handler = (e) => {
      // Match shortcut combos and fire callbacks
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [shortcuts]);
}
