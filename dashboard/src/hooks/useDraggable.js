/**
 * useDraggable — makes a component freely draggable using pointer capture.
 *
 * Usage:
 *   const { containerRef, posStyle, dragHandleProps } = useDraggable();
 *
 *   <div ref={containerRef} style={posStyle} className="fixed ...">
 *     <div {...dragHandleProps}>⠿</div>   ← drag from here
 *     ...content...
 *   </div>
 *
 * - `containerRef`   attach to the element you want to move
 * - `posStyle`       apply to the same element (left/top override when dragged)
 * - `dragHandleProps` spread onto the element the user grabs to initiate drag
 */

import { useRef, useState, useCallback } from 'react';

export function useDraggable() {
    const [pos, setPos] = useState(null); // null = use default CSS position
    const containerRef = useRef(null);
    const drag = useRef({ active: false, startX: 0, startY: 0, originX: 0, originY: 0 });

    const onPointerDown = useCallback((e) => {
        if (e.button !== 0) return;
        // Don't start a drag when interacting with buttons/links inside the drag handle
        if (e.target.closest('button, a, [role="button"]')) return;
        const container = containerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        drag.current = {
            active: true,
            startX: e.clientX,
            startY: e.clientY,
            originX: rect.left,
            originY: rect.top,
        };
        // Capture future pointer events on this handle so they arrive even when
        // the pointer leaves the element during a fast drag.
        e.currentTarget.setPointerCapture(e.pointerId);
        e.preventDefault();
    }, []);

    const onPointerMove = useCallback((e) => {
        if (!drag.current.active) return;
        const dx = e.clientX - drag.current.startX;
        const dy = e.clientY - drag.current.startY;
        // Clamp so the component stays visible within the viewport
        const x = Math.max(0, Math.min(drag.current.originX + dx, window.innerWidth - 80));
        const y = Math.max(0, Math.min(drag.current.originY + dy, window.innerHeight - 80));
        setPos({ x, y });
    }, []);

    const onPointerUp = useCallback(() => {
        drag.current.active = false;
    }, []);

    return {
        containerRef,
        posStyle: pos
            ? { position: 'fixed', left: pos.x, top: pos.y, bottom: 'auto', right: 'auto' }
            : {},
        dragHandleProps: {
            onPointerDown,
            onPointerMove,
            onPointerUp,
            style: { touchAction: 'none', cursor: 'grab' },
        },
    };
}
