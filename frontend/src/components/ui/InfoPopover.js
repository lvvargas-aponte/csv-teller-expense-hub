import React, { useCallback, useEffect, useId, useRef, useState } from 'react';

/**
 * The one explain-this widget. A real button toggles a panel it owns through
 * aria-controls, Escape closes it and hands focus back, and a click anywhere
 * else dismisses it. Hover opens it too, but only as a shortcut for people
 * who have a pointer — it is never the mechanism, and it is tracked
 * separately so a click on an already-hovered trigger opens rather than
 * closes.
 */
export default function InfoPopover({ label, title, className = '', children }) {
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const wrapRef = useRef(null);
  const triggerRef = useRef(null);
  const panelId = `info-${useId()}`;
  const open = pinned || hovered;

  const close = useCallback((returnFocus) => {
    setPinned(false);
    setHovered(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e) => {
      if (!wrapRef.current?.contains(e.target)) close(false);
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close(true);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, close]);

  return (
    <span ref={wrapRef} className={`eh-info ${className}`.trim()}>
      <button
        ref={triggerRef}
        type="button"
        className="eh-info-btn"
        aria-label={`About ${label}`}
        aria-expanded={open}
        aria-controls={panelId}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => setPinned((p) => !p)}
        onBlur={(e) => {
          if (!wrapRef.current?.contains(e.relatedTarget)) setPinned(false);
        }}
      >
        <span aria-hidden="true">i</span>
      </button>
      {open && (
        <div id={panelId} className="eh-info-panel" role="note">
          {title && <div className="eh-info-panel-title">{title}</div>}
          {children}
        </div>
      )}
    </span>
  );
}
