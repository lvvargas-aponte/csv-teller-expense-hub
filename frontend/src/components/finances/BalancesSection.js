import React, { useState, useMemo, useCallback } from 'react';
import Backdrop from '../ui/Backdrop';
import Field from '../ui/Field';
import Spin from '../ui/Spin';
import { fmt$, fmtSigned } from '../../utils/formatting';
import {
  addManualAccount,
  deleteManualAccount,
  updateAccountBalance,
} from '../../api/balances';
import { Z_BACKDROP_TOP } from '../../utils/zIndex';

function formatRelativeTime(isoString) {
  const diffMs = Date.now() - new Date(isoString + 'Z').getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 2) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  return `${Math.round(diffMin / 60)}h ago`;
}

export default function BalancesSection({ summary, loading, error, onRefresh, onMutate }) {
  const [showAddAcct, setShowAddAcct] = useState(false);
  const [newAcct,     setNewAcct]     = useState({
    institution: '', name: '', type: 'depository', available: '', ledger: '',
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [editingAcct, setEditingAcct] = useState(null);

  // Subtype labels Teller / users may attach to an investment account.
  // Kept in sync with backend ``analytics._INVESTMENT_SUBTYPES``; if those
  // expand, mirror the new entries here.
  const INVESTMENT_SUBTYPES = useMemo(
    () => new Set([
      '401k', '401(k)', '403b', '403(b)', 'ira', 'roth_ira', 'roth ira',
      'brokerage', 'hsa', 'investment', 'retirement', 'rollover_ira',
      'sep_ira', 'simple_ira', '529',
    ]),
    []
  );
  const isInvestment = useCallback(
    (a) => a.type === 'investment'
        || INVESTMENT_SUBTYPES.has((a.subtype || '').toLowerCase().trim()),
    [INVESTMENT_SUBTYPES]
  );

  const depository = useMemo(
    () => summary?.accounts?.filter((a) => a.type === 'depository' && !isInvestment(a)) ?? [],
    [summary, isInvestment]
  );
  const credit = useMemo(
    () => summary?.accounts?.filter((a) => a.type === 'credit') ?? [],
    [summary]
  );
  const investments = useMemo(
    () => summary?.accounts?.filter((a) => isInvestment(a)) ?? [],
    [summary, isInvestment]
  );

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
    } catch {
      /* silent */
    }
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
    <div className="finances-section">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="finances-section-title" style={{ margin: 0 }}>Account Balances</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {summary?.cache_fetched_at && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Updated {formatRelativeTime(summary.cache_fetched_at)}
            </span>
          )}
          <button type="button" className="btn btn-secondary btn-sm"
                  onClick={onRefresh} disabled={loading}
                  title="Fetch latest balances from Teller">
            {loading ? <Spin /> : '↺'}
          </button>
          <button type="button" className="btn btn-secondary btn-sm"
                  onClick={() => { setShowAddAcct((v) => !v); setSaveError(null); }}>
            {showAddAcct ? 'Cancel' : '+ Add Account'}
          </button>
        </div>
      </div>

      {showAddAcct && (
        <div className="manual-acct-form">
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
              <input className="form-input" type="number" min="0" step="0.01"
                     placeholder="0.00" value={newAcct.available}
                     onChange={(e) => setNewAcct((a) => ({ ...a, available: e.target.value }))} />
            </Field>
          </div>
          <div className="form-row-2">
            <Field label="Ledger Balance ($)">
              <input className="form-input" type="number" min="0" step="0.01"
                     placeholder="0.00" value={newAcct.ledger}
                     onChange={(e) => setNewAcct((a) => ({ ...a, ledger: e.target.value }))} />
            </Field>
            <div className="field-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button type="button" className="btn btn-primary" onClick={handleSave}
                      disabled={saving || !newAcct.institution.trim() || !newAcct.name.trim()}>
                {saving ? <><Spin /> Saving…</> : 'Save Account'}
              </button>
            </div>
          </div>
          {saveError && (
            <div style={{ color: '#f87171', fontSize: 13, marginTop: 8 }}>{saveError}</div>
          )}
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>
      )}
      {error && (
        <div style={{ color: '#f87171', fontSize: 14 }}>{error}</div>
      )}

      {!loading && !error && summary && (
        <>
          <div
            data-testid="net-worth-card"
            className={'net-worth-card ' + (summary.net_worth >= 0 ? 'net-worth-card--positive' : 'net-worth-card--negative')}
          >
            <div className="net-worth-label">Net Worth</div>
            <div className="net-worth-value">{fmtSigned(summary.net_worth)}</div>
            <div style={{ display: 'flex', gap: 24, marginTop: 8, fontSize: 13, opacity: 0.8, flexWrap: 'wrap' }}>
              <span>Cash &amp; Savings: {fmt$(summary.total_cash ?? 0)}</span>
              <span>Credit Debt: {fmt$(summary.total_credit_debt ?? 0)}</span>
              {(summary.total_investments ?? 0) > 0 && (
                <span>Investments: {fmt$(summary.total_investments)}</span>
              )}
            </div>
          </div>

          {depository.length > 0  && <AccountList title="Cash & Savings"        accounts={depository}  onDelete={handleDelete} onEdit={setEditingAcct} />}
          {investments.length > 0 && <AccountList title="Investments / Retirement" accounts={investments} onDelete={handleDelete} onEdit={setEditingAcct} />}
          {credit.length > 0      && <AccountList title="Credit & Loans"          accounts={credit}      onDelete={handleDelete} onEdit={setEditingAcct} />}

          {depository.length === 0 && credit.length === 0 && investments.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              No account data found. Connect a bank via Teller or add one manually above.
            </div>
          )}
        </>
      )}

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

function AccountList({ title, accounts, onDelete, onEdit }) {
  return (
    <>
      <div className="balance-section-title">{title}</div>
      {accounts.map((acct) => (
        <div key={acct.id} className="balance-row">
          <div className="balance-row-info">
            <div className="balance-row-name">
              {acct.name}
              {acct.manual && <span className="manual-badge">Manual</span>}
            </div>
            <div className="balance-row-inst">{acct.institution}</div>
          </div>
          <div className="balance-row-amounts">
            {acct.type === 'credit' ? (
              <>
                <div className="balance-available">
                  {fmt$(acct.ledger ?? 0)}
                  <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>owed</span>
                </div>
                <div className="balance-ledger">
                  {fmt$(acct.available ?? 0)}
                  <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>avail credit</span>
                </div>
              </>
            ) : (
              <>
                <div className="balance-available">
                  {fmt$(acct.available ?? 0)}
                  <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>avail</span>
                </div>
                <div className="balance-ledger">
                  {fmt$(acct.ledger ?? 0)}
                  <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>ledger</span>
                </div>
              </>
            )}
            <button type="button" className="btn btn-ghost btn-sm"
                    onClick={() => onEdit(acct)}
                    style={{ padding: '1px 6px', marginLeft: 6 }}
                    aria-label="Edit balance">✎</button>
            {acct.manual && (
              <button type="button" className="btn btn-ghost btn-sm"
                      onClick={() => onDelete(acct.id)}
                      style={{ padding: '1px 6px', marginLeft: 2 }}
                      aria-label="Remove account">✕</button>
            )}
          </div>
        </div>
      ))}
    </>
  );
}


function EditBalanceModal({ acct, onSave, onClose }) {
  const [available, setAvailable] = useState(String(acct.available ?? 0));
  const [ledger,    setLedger]    = useState(String(acct.ledger    ?? 0));
  const [saving,    setSaving]    = useState(false);
  const [err,       setErr]       = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await onSave({ available, ledger });
    } catch (e2) {
      setErr(e2.response?.data?.detail || e2.message || 'Could not save balance');
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
            {err && (
              <div style={{ color: '#f87171', fontSize: 13, marginTop: 8 }}>{err}</div>
            )}
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
