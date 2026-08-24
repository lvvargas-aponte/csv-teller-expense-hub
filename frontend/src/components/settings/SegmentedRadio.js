import React, { useId } from 'react';

/**
 * Segmented single-choice control — a styled radio group, not a button row,
 * so arrow keys move between options and screen readers announce it as one
 * question with N answers.
 */
export default function SegmentedRadio({ label, value, onChange, options }) {
  const name = useId();
  return (
    <div className="set-segmented" role="radiogroup" aria-label={label}>
      {options.map((opt) => {
        const selected = value === opt.value;
        return (
          <label
            key={opt.value}
            className={`set-segment${selected ? ' set-segment--on' : ''}`}
          >
            <input
              type="radio"
              name={name}
              className="sr-only"
              value={opt.value}
              checked={selected}
              onChange={() => onChange(opt.value)}
            />
            {opt.label}
          </label>
        );
      })}
    </div>
  );
}
