import React, { useState } from 'react';
import Backdrop from '../../ui/Backdrop';
import Field from '../../ui/Field';
import Spin from '../../ui/Spin';
import { fmtSigned } from '../../../utils/formatting';
import { userMessage } from '../../../utils/errorMessage';
import { Z_BACKDROP_TOP } from '../../../utils/zIndex';

// Edit a manual account's balance. Previously lived inside BalancesSection;
// moved here when the Accounts page collapsed to a single set of lists.
export default function EditBalanceModal({ acct, onSave, onClose }) {
  // For manual accounts with linked transactions the live `available`/`ledger`
  // values are computed as starting + delta. Editing must target the *starting*
  // value, otherwise the user types one number and sees a different one after
  // save (starting gets set to the typed number, then display = typed + delta).
  const hasStarting = acct.manual && acct.starting_balance !== null && acct.starting_balance !== undefined;
  const initialValue = hasStarting ? acct.starting_balance : acct.available;
  const initialLedger = hasStarting ? acct.starting_balance : acct.ledger;
  const [available, setAvailable] = useState(String(initialValue ?? 0));
  const [ledger,    setLedger]    = useState(String(initialLedger ?? 0));
  const [saving,    setSaving]    = useState(false);
  const [err,       setErr]       = useState(null);
  const hasDelta = acct.manual && Math.abs(parseFloat(acct.txn_delta) || 0) >= 0.005;

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await onSave({ available, ledger });
    } catch (e2) {
      setErr(userMessage(e2, 'Could not save balance'));
      setSaving(false);
    }
  };

  return (
    <Backdrop onClose={onClose} zIndex={Z_BACKDROP_TOP}>
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Edit Balance</div>
            <div className="modal-sub">{acct.institution} · {acct.name}</div>
          </div>
          <button type="button" className="close-btn" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={submit}>
          <div className="modal-body">
            {hasDelta && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.5 }}>
                You&apos;re editing the <strong>starting balance</strong>. The live balance
                shown on the dashboard is starting + the {acct.linked_txn_count}{' '}
                linked transaction{acct.linked_txn_count === 1 ? '' : 's'}{' '}
                (currently {fmtSigned(parseFloat(acct.txn_delta) || 0)}).
              </div>
            )}
            <div className="form-row-2">
              {acct.type === 'credit' ? (
                <>
                  <Field label="Balance Owed ($)">
                    <input className="form-input" type="number" step="0.01"
                           value={ledger}
                           onChange={(e) => setLedger(e.target.value)} />
                  </Field>
                  <Field label="Available Credit ($)">
                    <input className="form-input" type="number" step="0.01"
                           value={available}
                           onChange={(e) => setAvailable(e.target.value)} />
                  </Field>
                </>
              ) : (
                <>
                  <Field label="Available Balance ($)">
                    <input className="form-input" type="number" step="0.01"
                           value={available}
                           onChange={(e) => setAvailable(e.target.value)} />
                  </Field>
                  <Field label="Ledger Balance ($)">
                    <input className="form-input" type="number" step="0.01"
                           value={ledger}
                           onChange={(e) => setLedger(e.target.value)} />
                  </Field>
                </>
              )}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
              Saving will record a new balance snapshot — your net-worth history preserves the change.
            </div>
            {err && <div className="ov-error">{err}</div>}
          </div>

          <div className="modal-footer" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? <><Spin /> Saving…</> : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </Backdrop>
  );
}
