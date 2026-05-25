import React, { useState } from 'react';
import Backdrop from '../../ui/Backdrop';
import Field from '../../ui/Field';
import Spin from '../../ui/Spin';
import { addManualAccount } from '../../../api/balances';
import { userMessage } from '../../../utils/errorMessage';
import { Z_BACKDROP_TOP } from '../../../utils/zIndex';

// Presets the modal title and the underlying account `type` field. The credit
// preset asks for "balance owed" (stored as ledger) and "available credit";
// depository asks for "available" + "ledger" balances directly.
const PRESETS = {
  credit: {
    title: 'Add Credit Card or Loan',
    sub:   'Track APR, limits, and due dates — these are stored locally.',
    type:  'credit',
    nameHint: 'e.g. Chase Sapphire',
    primaryLabel: 'Balance Owed ($)',
    secondaryLabel: 'Available Credit ($)',
    primaryField: 'ledger',
    secondaryField: 'available',
  },
  depository: {
    title: 'Add Bank Account or Savings',
    sub:   'Cash, checking, savings, money-market.',
    type:  'depository',
    nameHint: 'e.g. Ally Savings',
    primaryLabel: 'Available Balance ($)',
    secondaryLabel: 'Ledger Balance ($)',
    primaryField: 'available',
    secondaryField: 'ledger',
  },
};

export default function AddAccountModal({ kind, onClose, onSaved }) {
  const preset = PRESETS[kind] || PRESETS.depository;
  const [institution, setInstitution] = useState('');
  const [name, setName]               = useState('');
  const [primary, setPrimary]         = useState('');
  const [secondary, setSecondary]     = useState('');
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState(null);

  const canSave = institution.trim() && name.trim() && !saving;

  const submit = async (e) => {
    e.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await addManualAccount({
        institution: institution.trim(),
        name:        name.trim(),
        type:        preset.type,
        [preset.primaryField]:   parseFloat(primary)   || 0,
        [preset.secondaryField]: parseFloat(secondary) || 0,
      });
      onSaved?.();
      onClose();
    } catch (err) {
      setError(userMessage(err, 'Could not save — is the backend running?'));
      setSaving(false);
    }
  };

  return (
    <Backdrop onClose={onClose} zIndex={Z_BACKDROP_TOP}>
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">{preset.title}</div>
            <div className="modal-sub">{preset.sub}</div>
          </div>
          <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={submit}>
          <div className="modal-body">
            <div className="form-row-2">
              <Field label="Institution">
                <input className="form-input" type="text" autoFocus
                       placeholder="e.g. Chase"
                       value={institution}
                       onChange={(e) => setInstitution(e.target.value)} />
              </Field>
              <Field label="Account Name">
                <input className="form-input" type="text"
                       placeholder={preset.nameHint}
                       value={name}
                       onChange={(e) => setName(e.target.value)} />
              </Field>
            </div>
            <div className="form-row-2">
              <Field label={preset.primaryLabel}>
                <input className="form-input" type="number" step="0.01" min="0" placeholder="0.00"
                       value={primary}
                       onChange={(e) => setPrimary(e.target.value)} />
              </Field>
              <Field label={preset.secondaryLabel}>
                <input className="form-input" type="number" step="0.01" min="0" placeholder="0.00"
                       value={secondary}
                       onChange={(e) => setSecondary(e.target.value)} />
              </Field>
            </div>
            {error && <div className="ov-error">{error}</div>}
          </div>

          <div className="modal-footer" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={!canSave}>
              {saving ? <><Spin /> Saving…</> : 'Add account'}
            </button>
          </div>
        </form>
      </div>
    </Backdrop>
  );
}
