import React, { useState } from 'react';
import Backdrop from '../ui/Backdrop';
import { fmt$ } from '../../utils/formatting';

export default function SuggestPreviewModal({ result, onApply, onClose }) {
  const [rows, setRows] = useState(() =>
    (result.results || []).map((r) => ({
      id:          r.id,
      description: r.description,
      amount:      r.amount,
      category:    r.suggested_category || '',
      checked:     !!r.suggested_category,
    }))
  );

  const toggle = (id) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, checked: !r.checked } : r)));

  const setCategory = (id, value) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, category: value } : r)));

  const skippedCount = (result.skipped_ids || []).length;
  const aiAvailable  = result.ai_available !== false;

  const ready = rows.filter((r) => r.checked && r.category.trim());
  const handleApply = () => {
    const items = ready.map((r) => ({
      transaction_id: r.id,
      category:       r.category.trim(),
    }));
    onApply(items);
  };

  return (
    <Backdrop onClose={onClose}>
      <div className="modal" style={{ maxWidth: 720 }}>
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Suggest categories</div>
            <div className="modal-sub">
              {rows.length} ready
              {skippedCount > 0 && ` · ${skippedCount} already categorized, skipped`}
            </div>
          </div>
          <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {!aiAvailable && (
            <div style={{
              color: '#f87171', fontSize: 13, marginBottom: 12,
              padding: 8, border: '1px solid #f87171', borderRadius: 6,
            }}>
              Ollama is not running — start it to get suggestions. You can still
              type categories manually below.
            </div>
          )}

          {rows.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
              No transactions to suggest for.
            </div>
          ) : (
            <>
              <datalist id="suggest-cats">
                {(result.candidates || []).map((c) => <option key={c} value={c} />)}
              </datalist>
              <table className="txn-table" style={{ fontSize: 13 }}>
                <thead>
                  <tr>
                    <th className="col-checkbox"></th>
                    <th>Description</th>
                    <th className="col-amount">Amount</th>
                    <th>Category</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td className="col-checkbox">
                        <input type="checkbox" checked={r.checked}
                               onChange={() => toggle(r.id)}
                               aria-label={`Include ${r.description}`} />
                      </td>
                      <td style={{
                        maxWidth: 260, overflow: 'hidden',
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }} title={r.description}>{r.description}</td>
                      <td className="col-amount">{fmt$(r.amount)}</td>
                      <td>
                        <input className="form-input" type="text"
                               list="suggest-cats"
                               value={r.category}
                               onChange={(e) => setCategory(r.id, e.target.value)}
                               placeholder="(none)"
                               style={{ padding: '4px 8px', fontSize: 13 }} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary"
                  onClick={handleApply}
                  disabled={ready.length === 0}>
            Apply ({ready.length})
          </button>
        </div>
      </div>
    </Backdrop>
  );
}
