import React, { useState, useRef, useEffect, useId } from 'react';

/**
 * Custom select dropdown.
 *
 * Props:
 *   value       – currently selected value
 *   onChange    – called with the new value string
 *   options     – [{ value, label }]
 *   placeholder – label shown when nothing is selected (optional)
 *   className   – extra class on the trigger button (optional)
 */
export default function Select({ value, onChange, options, placeholder, className = '', 'aria-label': ariaLabel }) {
  const [open, setOpen]       = useState(false);
  const [focused, setFocused] = useState(null); // index of keyboard-focused option
  const containerRef          = useRef(null);
  const listRef               = useRef(null);
  const id                    = useId();
  const listId                = `select-list-${id}`;

  const selectedLabel = options.find((o) => o.value === value)?.label ?? placeholder ?? '';

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (!containerRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Scroll focused option into view
  useEffect(() => {
    if (focused === null || !listRef.current) return;
    const item = listRef.current.querySelector(`[data-idx="${focused}"]`);
    item?.scrollIntoView?.({ block: 'nearest' });
  }, [focused]);

  const openList = () => {
    const idx = options.findIndex((o) => o.value === value);
    setFocused(idx >= 0 ? idx : 0);
    setOpen(true);
  };

  const select = (val) => {
    onChange(val);
    setOpen(false);
    setFocused(null);
    containerRef.current?.querySelector('[role="combobox"]').focus();
  };

  const handleKeyDown = (e) => {
    if (!open) {
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(e.key)) {
        e.preventDefault();
        openList();
      }
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
      containerRef.current?.querySelector('[role="combobox"]').focus();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocused((f) => Math.min((f ?? -1) + 1, options.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocused((f) => Math.max((f ?? options.length) - 1, 0));
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (focused !== null) select(options[focused].value);
    } else if (e.key === 'Tab') {
      setOpen(false);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`custom-select ${open ? 'custom-select--open' : ''}`}
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        aria-activedescendant={open && focused !== null ? `${id}-opt-${focused}` : undefined}
        className={`custom-select__trigger ${className}`}
        onClick={() => (open ? setOpen(false) : openList())}
      >
        <span className="custom-select__label">{selectedLabel}</span>
        <svg className="custom-select__chevron" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M6 8L1 3h10z" />
        </svg>
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="custom-select__list"
        >
          {options.map((opt, idx) => {
            const isSelected = opt.value === value;
            const isFocused  = idx === focused;
            return (
              <li
                key={opt.value}
                id={`${id}-opt-${idx}`}
                data-idx={idx}
                role="option"
                aria-selected={isSelected}
                className={[
                  'custom-select__option',
                  isSelected ? 'custom-select__option--selected' : '',
                  isFocused  ? 'custom-select__option--focused'  : '',
                ].join(' ')}
                onMouseDown={(e) => { e.preventDefault(); select(opt.value); }}
                onMouseEnter={() => setFocused(idx)}
              >
                {isSelected && (
                  <svg className="custom-select__check" viewBox="0 0 12 12" aria-hidden="true">
                    <path d="M2 6l3 3 5-5" strokeWidth="1.8" stroke="currentColor" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
                {opt.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
