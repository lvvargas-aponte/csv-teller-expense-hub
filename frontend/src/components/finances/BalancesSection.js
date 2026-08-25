import React, { useState, useMemo, useCallback } from 'react';
import Backdrop from '../ui/Backdrop';
import Field from '../ui/Field';
import Spin from '../ui/Spin';
import { fmt$, fmtSigned, formatRelativeTime } from '../../utils/formatting';
import { userMessage } from '../../utils/errorMessage';
import {
  addManualAccount,
  deleteManualAccount,
  updateAccountBalance,
} from '../../api/balances';
import { Z_BACKDROP_TOP } from '../../utils/zIndex';
import { classifyAccountBucket } from '../../utils/accountBucket';

// Choose the icon + tinted background color for an account row based on its
// type/subtype. Hand-picked palette mirrors the design handoff.
function iconForAccount(acct, isInvestment) {
  if (acct.type === 'credit') {
    const lname = (acct.name || '').toLowerCase();
    if (lname.includes('jet') || lname.includes('air') || lname.includes('travel')) {
      return { icon: '✈️', bg: '#ede9fe' };
    }
    return { icon: '💳', bg: '#fee2e2' };
  }
  if (isInvestment) return { icon: '📈', bg: '#dbeafe' };
  return { icon: '🏦', bg: '#dbeafe' };
}

const isInvestment = (a) => classifyAccountBucket(a) === 'investment';

export default function BalancesSection({ summary, loading, error, onRefresh, onMutate }) {
  const [showAddAcct, setShowAddAcct] = useState(false);
  const [newAcct,     setNewAcct]     = useState({
    institution: '', name: '', type: 'depository', available: '', ledger: '',
  });
  const [saving,    setSaving]    = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [editingAcct, setEditingAcct] = useState(null);

  const depository = useMemo(
    () => summary?.accounts?.filter((a) => classifyAccountBucket(a) === 'cash') ?? [],
    [summary]
  );
  const investments = useMemo(
    () => summary?.accounts?.filter((a) => isInvestment(a)) ?? [],
    [summary]
  );
  // Paid-off cards stay listed: a card you just cleared used to vanish from
  // the page where you would go to close or edit it.
  const credit = useMemo(
    () => summary?.accounts?.filter((a) => classifyAccountBucket(a) === 'credit') ?? [],
    [summary]
  );

  const totalCash        = summary?.total_cash ?? 0;
  const totalInvestments = summary?.total_investments ?? 0;
  const totalCredit      = summary?.total_credit_debt ?? 0;
  const netWorth         = summary?.net_worth ?? 0;

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await addManualAccount({
        institution: newAcct.institution.trim(),
        name:        newAcct.name.trim(),
        type:        newAcct.type,
        available:   parseFloat(newAcct.available) || 0,
        ledger:      parseFloat(newAcct.ledger)    || 0,
      });
      setShowAddAcct(false);
      setNewAcct({ institution: '', name: '', type: 'depository', available: '', ledger: '' });
      onMutate?.();
    } catch {
      setSaveError('Could not save — is the backend running?');
    } finally {
      setSaving(false);
    }
  }, [newAcct, onMutate]);

  const handleDelete = useCallback(async (id) => {
    try {
      await deleteManualAccount(id);
      onMutate?.();
    } catch { /* silent */ }
  }, [onMutate]);

  const handleEditSave = useCallback(async ({ available, ledger }) => {
    if (!editingAcct) return;
    const payload = {};
    if (available !== '') payload.available = parseFloat(available) || 0;
    if (ledger    !== '') payload.ledger    = parseFloat(ledger)    || 0;
    await updateAccountBalance(editingAcct.id, payload);
    setEditingAcct(null);
    onMutate?.();
  }, [editingAcct, onMutate]);

  return (
    <div className="ov-card">
      {/* Net Worth banner inline at the top of the card */}
      <div className="ov-nw-banner">
        <div className="ov-nw-left">
          <h2 className="ov-nw-label">Net Worth</h2>
          <div className={`ov-nw-value${netWorth < 0 ? ' ov-nw-value--neg' : ''}`}>
            {fmtSigned(netWorth)}
          </div>
          <div className="ov-nw-sub">
            <span><span aria-hidden="true">🏦</span> Cash &amp; Savings: {fmt$(totalCash)}</span>
            <span><span aria-hidden="true">💳</span> Credit Debt: {fmt$(totalCredit)}</span>
            {totalInvestments > 0 && (
              <span><span aria-hidden="true">📈</span> Investments: {fmt$(totalInvestments)}</span>
            )}
          </div>
          {summary?.cache_fetched_at && (
            <div className="ov-nw-updated">Updated {formatRelativeTime(summary.cache_fetched_at)}</div>
          )}
        </div>
        <div className="ov-nw-actions">
          <button
            type="button"
            className="ov-nw-btn"
            onClick={onRefresh}
            disabled={loading}
            title="Fetch latest balances"
          >
            {loading ? <><Spin /> Refreshing…</> : '↺ Refresh'}
          </button>
          <button
            type="button"
            className="ov-nw-btn"
            onClick={() => { setShowAddAcct((v) => !v); setSaveError(null); }}
          >
            {showAddAcct ? 'Cancel' : '+ Add Account'}
          </button>
        </div>
      </div>

      <div className="ov-card-body" style={{ paddingTop: 12 }}>
        {showAddAcct && (
          <div className="ov-add-form">
            <div className="form-row-2">
              <Field label="Institution">
                <input className="form-input" type="text" placeholder="e.g. Chase"
                       value={newAcct.institution}
                       onChange={(e) => setNewAcct((a) => ({ ...a, institution: e.target.value }))} />
              </Field>
              <Field label="Account Name">
                <input className="form-input" type="text" placeholder="e.g. Savings"
                       value={newAcct.name}
                       onChange={(e) => setNewAcct((a) => ({ ...a, name: e.target.value }))} />
              </Field>
            </div>
            <div className="form-row-2">
              <Field label="Type">
                <select className="form-input" value={newAcct.type}
                        onChange={(e) => setNewAcct((a) => ({ ...a, type: e.target.value }))}>
                  <option value="depository">Checking / Savings</option>
                  <option value="credit">Credit Card / Loan</option>
                  <option value="investment">Investment / Retirement (401k, IRA, Brokerage)</option>
                </select>
              </Field>
              <Field label="Available Balance ($)">
                <input className="form-input" type="number" min="0" step="0.01" placeholder="0.00"
                       value={newAcct.available}
                       onChange={(e) => setNewAcct((a) => ({ ...a, available: e.target.value }))} />
              </Field>
            </div>
            <div className="form-row-2">
              <Field label="Ledger Balance ($)">
                <input className="form-input" type="number" min="0" step="0.01" placeholder="0.00"
                       value={newAcct.ledger}
                       onChange={(e) => setNewAcct((a) => ({ ...a, ledger: e.target.value }))} />
              </Field>
              <div className="field-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button type="button" className="ov-btn ov-btn-primary" onClick={handleSave}
                        disabled={saving || !newAcct.institution.trim() || !newAcct.name.trim()}>
                  {saving ? <><Spin /> Saving…</> : 'Save Account'}
                </button>
              </div>
            </div>
            {saveError && <div className="ov-error">{saveError}</div>}
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', padding: '20px 0', color: '#6b7280' }}>
            <Spin /> Loading…
          </div>
        )}
        {error && <div className="ov-error">{error}</div>}

        {!loading && !error && summary && (
          <>
            {depository.length > 0 && (
              <AccountList
                title="Cash & Savings"
                tagClass="ov-tag ov-tag-green"
                tagAmount={fmt$(totalCash)}
                accounts={depository}
                onDelete={handleDelete}
                onEdit={setEditingAcct}
              />
            )}
            {investments.length > 0 && (
              <AccountList
                title="Investments / Retirement"
                tagClass="ov-tag ov-tag-blue"
                tagAmount={fmt$(totalInvestments)}
                accounts={investments}
                onDelete={handleDelete}
                onEdit={setEditingAcct}
              />
            )}
            {credit.length > 0 && (
              <AccountList
                title="Credit & Loans"
                tagClass="ov-tag ov-tag-red"
                tagAmount={fmt$(totalCredit)}
                accounts={credit}
                onDelete={handleDelete}
                onEdit={setEditingAcct}
              />
            )}
            {depository.length === 0 && credit.length === 0 && investments.length === 0 && (
              <div style={{ color: '#6b7280', fontSize: 14, padding: '20px 0' }}>
                No account data found. Connect a bank via SimpleFIN or add one manually above.
              </div>
            )}
          </>
        )}
      </div>

      {editingAcct && (
        <EditBalanceModal
          acct={editingAcct}
          onSave={handleEditSave}
          onClose={() => setEditingAcct(null)}
        />
      )}
    </div>
  );
}

function AccountList({ title, tagClass, tagAmount, accounts, onDelete, onEdit }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="ov-section-header">
        <h3 style={{ margin: 0, font: 'inherit' }}>{title}</h3>
        <span className={tagClass} style={{ marginLeft: 'auto' }}>{tagAmount}</span>
      </div>
      {accounts.map((acct) => (
        <AccountRow key={acct.id} acct={acct} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </div>
  );
}

function AccountRow({ acct, onEdit, onDelete }) {
  const investment = isInvestment(acct);
  const { icon, bg } = iconForAccount(acct, investment);
  const isCredit = acct.type === 'credit';

  // Display amount: credit accounts show |ledger| (the amount owed); deposits/
  // investments show available. Sign drives the color class.
  const displayAmt = isCredit
    ? Math.abs(parseFloat(acct.ledger) || 0)
    : (parseFloat(acct.available) || 0);
  const isNeg = isCredit ? displayAmt > 0 : displayAmt < 0;
  const isZero = displayAmt === 0;
  const colorClass = isZero ? 'ov-bal-primary--zero'
                    : isNeg ? 'ov-bal-primary--neg'
                            : 'ov-bal-primary--pos';

  const secondaryLabel = isCredit ? '' : 'available';

  return (
    <div className="ov-balance-row">
      <div className="ov-acct-icon" style={{ background: bg }} aria-hidden="true">{icon}</div>
      <div className="ov-balance-info">
        <div className="ov-balance-name">
          {acct.name}
          {acct.manual && <span className="ov-tag-manual">Manual</span>}
          {isCredit && isZero && <span className="ov-tag-paid">Paid off</span>}
        </div>
        <div className="ov-balance-inst">{acct.institution}</div>
        {acct.manual && acct.linked_txn_count > 0 && (
          <div className="ov-balance-linked-meta" title="Live balance = starting balance + signed delta of linked transactions">
            Last updated {formatRelativeTime(acct.linked_last_date)} · from {acct.linked_txn_count} linked
            {' '}txn{acct.linked_txn_count === 1 ? '' : 's'}
          </div>
        )}
      </div>
      <div className="ov-balance-amounts">
        <div className="ov-balance-amount-col">
          <div className={`ov-bal-primary ${colorClass}`}>
            {(isCredit && displayAmt > 0 ? '-' : '') + fmt$(displayAmt)}
          </div>
          {secondaryLabel && <div className="ov-bal-secondary">{secondaryLabel}</div>}
        </div>
        <div className="ov-balance-actions">
          {acct.manual && (
            <button
              type="button"
              className="ov-icon-btn"
              onClick={() => onEdit(acct)}
              aria-label="Edit balance"
              title="Edit balance"
            ><span aria-hidden="true">✎</span></button>
          )}
          {acct.manual && (
            <button
              type="button"
              className="ov-icon-btn ov-icon-btn--danger"
              onClick={() => onDelete(acct.id)}
              aria-label="Remove account"
              title="Remove account"
            ><span aria-hidden="true">✕</span></button>
          )}
        </div>
      </div>
    </div>
  );
}

function EditBalanceModal({ acct, onSave, onClose }) {
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