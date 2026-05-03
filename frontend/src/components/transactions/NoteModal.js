import React, { useState } from 'react';
import Backdrop from '../ui/Backdrop';
import { fmtDate, fmt$ } from '../../utils/formatting';

export default function NoteModal({ txn, onSave, onClose }) {
  const [notes, setNotes] = useState(txn.notes || '');

  return (
    <Backdrop onClose={onClose}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">{txn.description}</div>
            <div className="modal-sub">{fmtDate(txn.date)} · {fmt$(txn.amount)}</div>
          </div>
          <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          <div className="field-group">
            <label className="field-label">Notes</label>
            <textarea
              className="form-input form-input--textarea"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add a note…"
              autoFocus
            />
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={() => onSave(notes)}>Save</button>
        </div>
      </div>
    </Backdrop>
  );
}
