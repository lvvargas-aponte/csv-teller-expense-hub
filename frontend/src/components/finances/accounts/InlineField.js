import React, { useEffect, useRef, useState } from 'react';

// Inline-editable cell. Renders a transparent text input that highlights on
// hover/focus and re-applies prefix/suffix on blur. Enter commits, Escape
// reverts, blur fires onChange with the parsed value.
//
// Props:
//   value     — current displayed value (number | string | null)
//   onChange  — fired with the parsed value on blur (string for text fields,
//               number or null for numeric fields)
//   type      — 'number' | 'text' (default 'text')
//   prefix    — string shown before value when not focused (e.g. '$')
//   suffix    — string shown after value when not focused (e.g. '%')
//   align     — 'left' | 'right' (default 'left')
//   placeholder — text shown when value is empty
//   className — extra classes (e.g. 'due-urgent')
//   ariaLabel — accessible name, for fields with no visible <label>
//   inputMode — passed to <input> (defaults from type)
//   step, min, max — passed to <input>
export default function InlineField({
  value,
  onChange,
  type = 'text',
  prefix = '',
  suffix = '',
  align = 'left',
  placeholder = '—',
  className = '',
  ariaLabel,
  step,
  min,
  max,
}) {
  const ref = useRef(null);
  const [focused, setFocused] = useState(false);
  const [draft, setDraft] = useState(displayValue(value, prefix, suffix));
  const [savedValue, setSavedValue] = useState(value);

  // When the parent value updates (e.g. after server reload), refresh the
  // displayed string — but only when not focused, so we don't fight the user's
  // typing.
  useEffect(() => {
    if (!focused) {
      setDraft(displayValue(value, prefix, suffix));
      setSavedValue(value);
    }
  }, [value, prefix, suffix, focused]);

  const empty = (value === null || value === undefined) || value === '';

  const handleFocus = () => {
    setFocused(true);
    setDraft((value === null || value === undefined) ? '' : String(value));
    requestAnimationFrame(() => ref.current?.select());
  };

  const handleBlur = () => {
    setFocused(false);
    const parsed = parseDraft(draft, type);
    setDraft(displayValue(parsed, prefix, suffix));
    if (!sameValue(parsed, savedValue)) {
      setSavedValue(parsed);
      onChange?.(parsed);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      ref.current?.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setDraft(displayValue(savedValue, prefix, suffix));
      // Defer blur so React picks up the reverted draft first
      setTimeout(() => ref.current?.blur(), 0);
    }
  };

  return (
    <input
      ref={ref}
      className={`ifield ${empty && !focused ? 'ifield-empty' : ''} ${align === 'right' ? 'ifield-right' : ''} ${className}`}
      // We use type="text" universally so prefix/suffix display works; numeric
      // validation happens on parse. inputMode hints to mobile keyboards.
      type="text"
      aria-label={ariaLabel}
      inputMode={type === 'number' ? 'decimal' : 'text'}
      value={draft}
      placeholder={placeholder}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={handleKeyDown}
      step={step}
      min={min}
      max={max}
    />
  );
}

function displayValue(v, prefix, suffix) {
  if ((v === null || v === undefined) || v === '') return '';
  return `${prefix}${v}${suffix}`;
}

function parseDraft(draft, type) {
  const trimmed = (draft || '').trim();
  if (trimmed === '') return null;
  if (type === 'number') {
    const n = parseFloat(trimmed.replace(/[^0-9.-]/g, ''));
    return Number.isFinite(n) ? n : null;
  }
  return trimmed;
}

function sameValue(a, b) {
  if ((a === null || a === undefined) && ((b === null || b === undefined) || b === '')) return true;
  if ((b === null || b === undefined) && ((a === null || a === undefined) || a === '')) return true;
  return a === b;
}
