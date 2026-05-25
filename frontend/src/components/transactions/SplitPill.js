import React from 'react';

export default function SplitPill({ value, onChange, disabled }) {
  return (
    <div className="tx-split-pill" role="group" aria-label="Split type">
      <button
        type="button"
        className={`tx-sp-opt${value === 'personal' ? ' tx-sp-opt--active-personal' : ''}`}
        onClick={() => onChange('personal')}
        disabled={disabled}
        aria-pressed={value === 'personal'}
        aria-label="Personal"
        title="Personal"
      >P</button>
      <button
        type="button"
        className={`tx-sp-opt${value === 'shared' ? ' tx-sp-opt--active-shared' : ''}`}
        onClick={() => onChange('shared')}
        disabled={disabled}
        aria-pressed={value === 'shared'}
        aria-label="Split 50/50"
        title="Split 50/50"
      >½</button>
    </div>
  );
}
