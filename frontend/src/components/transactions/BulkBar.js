import React from 'react';
import { fmt$ } from '../../utils/formatting';
import Spin from '../ui/Spin';

export default function BulkBar({
  selectedCount,
  sharedSelectedAmt,
  onMarkPersonal,
  onMark5050,
  onMarkReviewed,
  onSuggest,
  onClear,
  suggesting,
}) {
  return (
    <div className="tx-bulk-bar">
      <span className="tx-bulk-count">{selectedCount} selected</span>
      {sharedSelectedAmt > 0 && (
        <span className="tx-bulk-owed">· {fmt$(sharedSelectedAmt)} owed</span>
      )}
      <div className="tx-bulk-spacer" />
      <button type="button" className="tx-bulk-btn tx-bulk-btn--ghost" onClick={onMarkPersonal}>
        Mark personal
      </button>
      <button type="button" className="tx-bulk-btn tx-bulk-btn--green" onClick={onMark5050}>
        Split 50/50
      </button>
      {onMarkReviewed && (
        <button
          type="button"
          className="tx-bulk-btn tx-bulk-btn--ghost"
          onClick={onMarkReviewed}
          title="Mark selected as reviewed"
        >
          ✓ Mark reviewed
        </button>
      )}
      {onSuggest && (
        <button
          type="button"
          className="tx-bulk-btn tx-bulk-btn--ghost"
          onClick={onSuggest}
          disabled={suggesting}
          title="Ask the local AI to suggest categories"
        >
          {suggesting ? <><Spin /> Thinking…</> : '✨ Suggest'}
        </button>
      )}
      <button
        type="button"
        className="tx-bulk-btn tx-bulk-btn--deselect"
        onClick={onClear}
        aria-label="Clear selection"
      >✕</button>
    </div>
  );
}
