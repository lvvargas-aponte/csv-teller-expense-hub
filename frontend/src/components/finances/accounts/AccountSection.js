import React, { useState } from 'react';
import { fmt$ } from '../../../utils/formatting';

// Collapsible account group. Header shows title, account count and the group
// total; the body is the white list card.
export default function AccountSection({
  title,
  count,
  total,
  defaultOpen = true,
  children,
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="acct-section">
      <h2 className="acct-section-heading">
        <button
          type="button"
          className="acct-section-head"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
        <span className={`acct-chevron${open ? ' is-open' : ''}`} aria-hidden="true">▶</span>
        <span className="acct-section-title">{title}</span>
        <span className="acct-section-count">{count}</span>
        {(total !== null && total !== undefined) && (
          <span className="acct-section-total">{fmt$(total)}</span>
        )}
        </button>
      </h2>
      {open && <div className="acct-list">{children}</div>}
    </section>
  );
}
