import React, { useState } from 'react';
import Backdrop from '../../ui/Backdrop';
import Field from '../../ui/Field';
import Spin from '../../ui/Spin';
import { addManualAccount } from '../../../api/balances';
import { upsertAccountDetails } from '../../../api/accountDetails';
import { userMessage } from '../../../utils/errorMessage';
import { toYMD } from '../../../utils/formatting';
import { Z_BACKDROP_TOP } from '../../../utils/zIndex';

// Presets the modal title and the underlying account `type` field. The credit
// preset asks for "balance owed" (stored as ledger) and "available credit";
// depository asks for "available" + "ledger" balances directly. The asset
// preset asks for one value and the date it was true — a house has no bank,
// so there is no institution and no second balance. `singleValue` marks any
// preset (asset or otherwise) that has one figure the user knows, not two —
// see the `submit` comment on why it goes into both stored fields.
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
  asset: {
    title: 'Add Property or Vehicle',
    sub:   'Counts toward net worth. Nothing estimates it for you — you set the value, and the app tells you when it is getting old.',
    type:  'asset',
    isAsset: true,
    singleValue: true,
    nameHint: 'e.g. Maple Street',
    primaryLabel: 'Current Value ($)',
    primaryField: 'available',
    secondaryField: 'ledger',
  },
  investment: {
    title: 'Investment / Retirement (401k, IRA, Brokerage)',
    sub:   'Track a brokerage or retirement account manually — these are stored locally.',
    type:  'investment',
    singleValue: true,
    nameHint: 'e.g. Fidelity 401(k)',
    primaryLabel: 'Current Balance ($)',
    primaryField: 'available',
    secondaryField: 'ledger',
  },
};

const ASSET_SUBTYPES = [
  ['home', 'Home'],
  ['vehicle', 'Vehicle'],
  ['other', 'Other'],
];

export default function AddAccountModal({ kind, onClose, onSaved }) {
  const preset = PRESETS[kind] || PRESETS.depository;
  const [institution, setInstitution] = useState('');
  const [name, setName]               = useState('');
  const [subtype, setSubtype]         = useState('home');
  const [valuedOn, setValuedOn]       = useState(() => toYMD(new Date()));
  const [primary, setPrimary]         = useState('');
  const [secondary, setSecondary]     = useState('');
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState(null);

  const canSave = (preset.isAsset || institution.trim()) && name.trim() && !saving;

  const submit = async (e) => {
    e.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const value = parseFloat(primary) || 0;
      const created = await addManualAccount({
        institution: preset.isAsset ? '' : institution.trim(),
        name:        name.trim(),
        type:        preset.type,
        ...(preset.isAsset ? { subtype } : {}),
        [preset.primaryField]:   value,
        // A single-value account (a real asset, a manually-tracked
        // investment) has one figure the user knows, not two. Storing it in
        // both fields keeps every consumer agreeing on the value regardless
        // of which one it reads — accountMath.js and the backend disagree on
        // that preference, and a second, different number in the other field
        // would surface as two different totals for the same account.
        [preset.secondaryField]: preset.singleValue ? value : (parseFloat(secondary) || 0),
      });
      if (preset.isAsset && created?.data?.id) {
        await upsertAccountDetails(created.data.id, { valuation_updated_on: valuedOn });
      }
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
              {preset.isAsset ? (
                <Field label="Kind">
                  <select className="form-input" value={subtype}
                          onChange={(e) => setSubtype(e.target.value)}>
                    {ASSET_SUBTYPES.map(([v, label]) => (
                      <option key={v} value={v}>{label}</option>
                    ))}
                  </select>
                </Field>
              ) : (
                <Field label="Institution">
                  <input className="form-input" type="text" autoFocus
                         placeholder="e.g. Chase"
                         value={institution}
                         onChange={(e) => setInstitution(e.target.value)} />
                </Field>
              )}
              <Field label={preset.isAsset ? 'Name' : 'Account Name'}>
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
              {preset.isAsset ? (
                <Field label="Value as of">
                  <input className="form-input" type="date"
                         value={valuedOn}
                         onChange={(e) => setValuedOn(e.target.value)} />
                </Field>
              ) : preset.singleValue ? null : (
                <Field label={preset.secondaryLabel}>
                  <input className="form-input" type="number" step="0.01" min="0" placeholder="0.00"
                         value={secondary}
                         onChange={(e) => setSecondary(e.target.value)} />
                </Field>
              )}
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
