import React, { useEffect, useRef, useState } from 'react';
import { aprBadgeClass } from './helpers';

// `readOnly` renders the badge without the click-to-edit affordance: an
// account's APR is edited in the Credit cards drawer, not here.
export function AprCell({ value, onChange, readOnly = false }) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(value || '');
  const inputRef = useRef(null);

  useEffect(() => { setDraft(value || ''); }, [value]);

  const start = () => {
    setEditing(true);
    setDraft(value || '');
    setTimeout(() => inputRef.current?.focus(), 0);
  };
  const commit = () => {
    onChange(draft);
    setEditing(false);
  };
  const onKey = (e) => {
    if (e.key === 'Enter')  commit();
    if (e.key === 'Escape') setEditing(false);
  };

  if (editing && !readOnly) {
    return (
      <div className="ov-apr-cell">
        <input
          ref={inputRef}
          className="ov-apr-edit-input"
          type="number" min="0" step="0.01"
          placeholder="24.99"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKey}
          aria-label="APR percent"
        />
        <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>%</span>
      </div>
    );
  }

  const v = parseFloat(value) || 0;

  if (readOnly) {
    return (
      <div className="ov-apr-cell">
        {v > 0
          ? <span className={`ov-apr-badge ${aprBadgeClass(value)}`}>{v}%</span>
          : <span className="ov-apr-empty ov-apr-empty--static">No APR</span>}
      </div>
    );
  }

  return (
    <div className="ov-apr-cell">
      {v > 0 ? (
        <button
          type="button"
          className={`ov-apr-badge ${aprBadgeClass(value)}`}
          onClick={start}
          title="Click to edit"
        >{v}%</button>
      ) : (
        <button type="button" className="ov-apr-empty" onClick={start}>
          + set APR
        </button>
      )}
    </div>
  );
}

export function AprLegend() {
  const [show, setShow] = useState(false);
  return (
    <div className="ov-apr-info-wrap">
      <button
        type="button"
        className="ov-apr-info-btn"
        aria-label="APR color guide"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
      ><span aria-hidden="true">ⓘ</span></button>
      {show && (
        <div className="ov-apr-tooltip" role="tooltip">
          <div className="ov-apr-tooltip-title">APR color guide</div>
          {[
            { cls: 'ov-apr-badge--low',  label: '< 20% — Low' },
            { cls: 'ov-apr-badge--med',  label: '20–24% — Medium' },
            { cls: 'ov-apr-badge--high', label: '≥ 25% — High' },
          ].map((row) => (
            <div key={row.label} className="ov-apr-tooltip-row">
              <span className={`ov-apr-tooltip-swatch ${row.cls}`} aria-hidden="true">●</span>
              <span>{row.label}</span>
            </div>
          ))}
          <div className="ov-apr-tooltip-hint">Click any badge to edit</div>
        </div>
      )}
    </div>
  );
}
