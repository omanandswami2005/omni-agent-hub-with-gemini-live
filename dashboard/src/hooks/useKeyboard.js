/**
 * useKeyboard — Global keyboard shortcut handler.
 */

import { useEffect, useCallback } from 'react';

const INPUT_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

export function useKeyboard(shortcuts = {}) {
  const handler = useCallback(
    (e) => {
      // Skip when typing in input fields (unless shortcut explicitly allows it)
      const inInput = INPUT_TAGS.has(e.target.tagName) || e.target.isContentEditable;

      for (const [combo, callback] of Object.entries(shortcuts)) {
        if (!callback) continue;
        const parts = combo.toLowerCase().split('+');
        const key = parts.pop();
        const needsCtrl = parts.includes('ctrl') || parts.includes('cmd');
        const needsShift = parts.includes('shift');
        const needsAlt = parts.includes('alt');
        const allowInInput = parts.includes('global');

        if (inInput && !allowInInput && !needsCtrl) continue;
        if (needsCtrl && !(e.ctrlKey || e.metaKey)) continue;
        if (needsShift && !e.shiftKey) continue;
        if (needsAlt && !e.altKey) continue;

        const eventKey = e.key.toLowerCase();
        if (eventKey === key || e.code.toLowerCase() === key) {
          e.preventDefault();
          callback(e);
        }
      }
    },
    [shortcuts],
  );

  useEffect(() => {
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handler]);
}
