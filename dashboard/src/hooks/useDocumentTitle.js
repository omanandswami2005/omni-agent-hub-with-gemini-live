/**
 * Hook: useDocumentTitle — Sets the document title for the current page.
 */

import { useEffect } from 'react';
import { APP_NAME } from '@/lib/constants';

export function useDocumentTitle(title) {
    useEffect(() => {
        const prev = document.title;
        document.title = title ? `${title} — ${APP_NAME}` : `${APP_NAME} — Speak anywhere. Act everywhere.`;
        return () => {
            document.title = prev;
        };
    }, [title]);
}
