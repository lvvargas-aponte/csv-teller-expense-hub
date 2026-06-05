import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

// Combobox for selecting / creating / removing a category.
// - Click the input to open a dropdown of all known categories.
// - Click an option to select it (commits immediately).
// - Type to filter; press Enter on a non-matching value to create it.
// - Each option in the open dropdown has an × button to remove that
//   category globally (clears it from every transaction using it).
export default function CategoryCombobox({
  value,
  categories = [],
  onChange,
  onRemoveCategory,
  placeholder = 'Select or type…',
  compact = false,
}) {
  const [draft, setDraft] = useState(value || '');
  const [open, setOpen] = useState(false);
  const [panelStyle, setPanelStyle] = useState(null);
  const wrapRef = useRef(null);
  const rowRef = useRef(null);
  const panelRef = useRef(null);

  useEffect(() => { setDraft(value || ''); }, [value]);

  const updatePanelPos = useCallback(() => {
    if (!rowRef.current) return;
    const r = rowRef.current.getBoundingClientRect();
    setPanelStyle({
      position: 'fixed',
      top: r.bottom + 4,
      left: r.left,
      width: Math.max(r.width, 220),
    });
  }, []);

  useLayoutEffect(() => {
    if (!open) return undefined;
    updatePanelPos();
    window.addEventListener('scroll', updatePanelPos, true);
    window.addEventListener('resize', updatePanelPos);
    return () => {
      window.removeEventListener('scroll', updatePanelPos, true);
      window.removeEventListener('resize', updatePanelPos);
    };
  }, [open, updatePanelPos]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      const target = e.target;
      const insideWrap = wrapRef.current && wrapRef.current.contains(target);
      const insidePanel = panelRef.current && panelRef.current.contains(target);
      if (!insideWrap && !insidePanel) {
        setOpen(false);
        commitIfChanged(draft);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, draft]);

  const commitIfChanged = (next) => {
    const trimmed = (next || '').trim();
    if (trimmed === (value || '').trim()) return;
    onChange(trimmed);
  };

  const handleSelect = (name) => {
    setDraft(name);
    setOpen(false);
    commitIfChanged(name);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      setOpen(false);
      commitIfChanged(draft);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setDraft(value || '');
      setOpen(false);
    } else if (e.key === 'ArrowDown' && !open) {
      setOpen(true);
    }
  };

  const handleRemove = async (e, name) => {
    e.stopPropagation();
    if (!onRemoveCategory) return;
    const ok = window.confirm(
      `Remove category "${name}"?\n\nThis will clear it from every transaction currently using it.`
    );
    if (!ok) return;
    try {
      const result = await onRemoveCategory(name);
      if (result && result.cleared_txn_count > 0) {
        window.alert(`Cleared "${name}" from ${result.cleared_txn_count} transaction(s).`);
      }
    } catch {
      window.alert(`Could not remove "${name}".`);
    }
  };

  const draftTrim = (draft || '').trim();
  const filtered = draftTrim
    ? categories.filter((c) => c.toLowerCase().includes(draftTrim.toLowerCase()))
    : categories;
  const exactMatch = categories.some((c) => c.toLowerCase() === draftTrim.toLowerCase());
  const showCreateOption = draftTrim && !exactMatch;

  return (
    <div
      ref={wrapRef}
      className={`cat-combo${compact ? ' cat-combo--compact' : ''}${open ? ' cat-combo--open' : ''}`}
    >
      <div className="cat-combo-row" ref={rowRef}>
        <input
          className="cat-combo-input"
          type="text"
          value={draft}
          placeholder={placeholder}
          onChange={(e) => { setDraft(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          className="cat-combo-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Close categories' : 'Open categories'}
          tabIndex={-1}
        >▾</button>
      </div>

      {open && panelStyle && createPortal(
        <div
          ref={panelRef}
          className="cat-combo-panel cat-combo-panel--portal"
          role="listbox"
          style={panelStyle}
        >
          {filtered.length === 0 && !showCreateOption && (
            <div className="cat-combo-empty">No categories yet — type one to add it.</div>
          )}
          {filtered.map((c) => {
            const isSelected = c.toLowerCase() === (value || '').toLowerCase();
            return (
              <div
                key={c}
                role="option"
                aria-selected={isSelected}
                className={`cat-combo-option${isSelected ? ' cat-combo-option--selected' : ''}`}
                onMouseDown={(e) => { e.preventDefault(); handleSelect(c); }}
              >
                <span className="cat-combo-option-label">{c}</span>
                {onRemoveCategory && (
                  <button
                    type="button"
                    className="cat-combo-remove"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={(e) => handleRemove(e, c)}
                    title={`Remove "${c}"`}
                    aria-label={`Remove ${c}`}
                  >×</button>
                )}
              </div>
            );
          })}
          {showCreateOption && (
            <div
              role="option"
              className="cat-combo-option cat-combo-option--create"
              onMouseDown={(e) => { e.preventDefault(); handleSelect(draftTrim); }}
            >
              <span>+ Add “{draftTrim}”</span>
            </div>
          )}
        </div>,
        document.body
      )}
    </div>
  );
}
