import React, { useState } from 'react';

export default function NoteExpandRow({ txn, colSpan, onSave, onClose }) {
  const [value, setValue] = useState(txn.notes || '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try { await onSave(value); } finally { setSaving(false); }
  };

  const onKey = (e) => {
    if (e.key === 'Enter')  { e.preventDefault(); save(); }
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  return (
    <tr className="tx-note-row">
      <td colSpan={colSpan}>
        <div className="tx-note-inner">
          <span className="tx-note-label">Note</span>
          <input
            className="tx-note-input"
            placeholder="Add a note for this transaction…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKey}
            autoFocus
            aria-label="Transaction note"
          />
          <button type="button" className="tx-note-save" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="tx-note-close" onClick={onClose} aria-label="Close note">✕</button>
        </div>
      </td>
    </tr>
  );
}
