import React, { useEffect, useRef, useState } from 'react';

const LEGEND = [
  { icon: 'DR', label: 'Debit', detail: 'Money going out. Click to flip to credit.' },
  { icon: 'CR', label: 'Credit', detail: 'Money coming in. Click to flip to debit.' },
  { icon: 'P',  label: 'Personal', detail: 'Your expense; not shared with anyone.' },
  { icon: '½',  label: 'Shared', detail: '50/50 split — use ⚖ to adjust the share.' },
  { icon: '✓',  label: 'Reviewed', detail: "You've looked at this row; hides from the default view." },
  { icon: '⚖',  label: 'Adjust split', detail: 'Edit how much each person owes on a shared transaction.' },
  { icon: '✎',  label: 'Add note', detail: 'Attach a short note to remember context (renders 📝 when set).' },
  { icon: '↗',  label: 'Tag as transfer', detail: 'Mark as an internal transfer to a manual account. Excluded from spending; credits the destination balance.' },
];

export default function IconLegend() {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="icon-legend-wrap">
      <button
        type="button"
        className="icon-legend-btn"
        onClick={() => setOpen((o) => !o)}
        title="What do these icons mean?"
        aria-label="Show icon legend"
        aria-expanded={open}
        aria-controls="icon-legend-panel"
      >?</button>
      {open && (
        <div
          id="icon-legend-panel"
          role="region"
          aria-label="Icon legend"
          className="icon-legend-panel"
        >
          <div className="icon-legend-title">Icon legend</div>
          {LEGEND.map((row) => (
            <div key={row.icon} className="icon-legend-row">
              <div className="icon-legend-icon">{row.icon}</div>
              <div>
                <div className="icon-legend-row-label">{row.label}</div>
                <div className="icon-legend-row-detail">{row.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
