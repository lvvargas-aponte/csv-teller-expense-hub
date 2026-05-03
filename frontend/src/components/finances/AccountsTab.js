import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Field from '../ui/Field';
import Spin from '../ui/Spin';
import { fmt$ } from '../../utils/formatting';
import { getBalancesSummary } from '../../api/balances';
import {
  getAllAccountDetails, upsertAccountDetails, deleteAccountDetails,
} from '../../api/accountDetails';

const BLANK = {
  apr: '', credit_limit: '', minimum_payment: '',
  statement_day: '', due_day: '', notes: '',
};

function daysUntilNextDue(dueDay) {
  if (!dueDay) return null;
  const today = new Date();
  const y = today.getFullYear();
  const m = today.getMonth();
  const thisMonth = new Date(y, m, dueDay);
  const nextMonth = new Date(y, m + 1, dueDay);
  const target = today.getDate() <= dueDay ? thisMonth : nextMonth;
  const diffMs = target.getTime() - new Date(y, m, today.getDate()).getTime();
  return Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)));
}

export default function AccountsTab() {
  const [accounts,  setAccounts]  = useState([]);
  const [detailsMap, setDetailsMap] = useState({});
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  const loadDetails = useCallback(async () => {
    try {
      const r = await getAllAccountDetails();
      setDetailsMap(r.data || {});
    } catch {
      setDetailsMap({});
    }
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getBalancesSummary(false)
      .then((r) => {
        const accts = r.data?.accounts ?? [];
        setAccounts(accts);
        return loadDetails();
      })
      .catch(() => setError('Could not load accounts — is the backend running?'))
      .finally(() => setLoading(false));
  }, [loadDetails]);

  useEffect(() => { load(); }, [load]);

  const credit      = useMemo(() => accounts.filter((a) => a.type === 'credit'),     [accounts]);
  const depository  = useMemo(() => accounts.filter((a) => a.type === 'depository'), [accounts]);

  const handleSave = useCallback(async (accountId, draft) => {
    await upsertAccountDetails(accountId, {
      apr:             draft.apr === '' ? null : parseFloat(draft.apr),
      credit_limit:    draft.credit_limit === '' ? null : parseFloat(draft.credit_limit),
      minimum_payment: draft.minimum_payment === '' ? null : parseFloat(draft.minimum_payment),
      statement_day:   draft.statement_day === '' ? null : parseInt(draft.statement_day, 10),
      due_day:         draft.due_day === '' ? null : parseInt(draft.due_day, 10),
      notes:           draft.notes,
    });
    await load();
  }, [load]);

  const handleClear = useCallback(async (accountId) => {
    try {
      await deleteAccountDetails(accountId);
    } catch { /* 404 is fine — nothing to clear */ }
    await load();
  }, [load]);

  if (loading) {
    return (
      <div className="finances-section">
        <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>
      </div>
    );
  }
  if (error) {
    return <div className="finances-section" style={{ color: '#f87171' }}>{error}</div>;
  }

  return (
    <>
      {credit.length > 0 && (
        <div className="finances-section">
          <h2 className="finances-section-title">Credit Cards &amp; Loans</h2>
          {credit.map((a) => (
            <AccountDetailsCard
              key={a.id} account={a} details={detailsMap[a.id]}
              onSave={(d) => handleSave(a.id, d)}
              onClear={() => handleClear(a.id)}
            />
          ))}
        </div>
      )}
      {depository.length > 0 && (
        <div className="finances-section">
          <h2 className="finances-section-title">Cash &amp; Savings</h2>
          {depository.map((a) => (
            <AccountDetailsCard
              key={a.id} account={a} details={detailsMap[a.id]}
              onSave={(d) => handleSave(a.id, d)}
              onClear={() => handleClear(a.id)}
            />
          ))}
        </div>
      )}
      {accounts.length === 0 && (
        <div className="finances-section" style={{ color: 'var(--text-muted)' }}>
          No accounts yet — connect a bank or add one manually from the Overview tab.
        </div>
      )}
    </>
  );
}

function AccountDetailsCard({ account, details, onSave, onClear }) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(BLANK);
  const [saving,  setSaving]  = useState(false);
  const [err,     setErr]     = useState(null);

  const beginEdit = () => {
    setDraft(details ? {
      apr:             details.apr ?? '',
      credit_limit:    details.credit_limit ?? '',
      minimum_payment: details.minimum_payment ?? '',
      statement_day:   details.statement_day ?? '',
      due_day:         details.due_day ?? '',
      notes:           details.notes ?? '',
    } : BLANK);
    setErr(null);
    setEditing(true);
  };

  const commit = async () => {
    setSaving(true);
    setErr(null);
    try {
      await onSave(draft);
      setEditing(false);
    } catch (e) {
      setErr(e.response?.data?.detail || 'Could not save.');
    } finally {
      setSaving(false);
    }
  };

  const isCredit = account.type === 'credit';
  const days = daysUntilNextDue(details?.due_day);

  return (
    <div className="balance-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div className="balance-row-name">
            {account.name}
            {account.manual && <span className="manual-badge">Manual</span>}
          </div>
          <div className="balance-row-inst">{account.institution}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          {isCredit ? (
            <>
              <div className="balance-available">{fmt$(account.ledger ?? 0)}
                <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>owed</span>
              </div>
              <div className="balance-ledger">{fmt$(account.available ?? 0)}
                <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>avail credit</span>
              </div>
            </>
          ) : (
            <>
              <div className="balance-available">{fmt$(account.available ?? 0)}
                <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>avail</span>
              </div>
              <div className="balance-ledger">{fmt$(account.ledger ?? 0)}
                <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 4 }}>ledger</span>
              </div>
            </>
          )}
        </div>
      </div>

      {!editing && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 13,
                      color: 'var(--text-muted)' }}>
          {isCredit && (
            <>
              <DetailPill label="APR"   value={details?.apr != null ? `${details.apr}%` : null} />
              <DetailPill label="Limit" value={details?.credit_limit != null ? fmt$(details.credit_limit) : null} />
              <DetailPill label="Min"   value={details?.minimum_payment != null ? fmt$(details.minimum_payment) : null} />
            </>
          )}
          <DetailPill label="Statement" value={details?.statement_day ? `day ${details.statement_day}` : null} />
          <DetailPill label="Due"       value={details?.due_day ? `day ${details.due_day}${days != null ? ` · in ${days}d` : ''}` : null} />
          {details?.notes && <DetailPill label="Note" value={details.notes} />}
          <button type="button" className="btn btn-secondary btn-sm"
                  style={{ marginLeft: 'auto' }} onClick={beginEdit}>
            {details ? 'Edit' : '+ Add details'}
          </button>
          {details && (
            <button type="button" className="btn btn-ghost btn-sm"
                    onClick={onClear} aria-label="Clear account details">✕</button>
          )}
        </div>
      )}

      {editing && (
        <div className="manual-acct-form">
          <div className="form-row-2">
            {isCredit && (
              <Field label="APR (%)">
                <input className="form-input" type="number" min="0" step="0.01" placeholder="24.99"
                       value={draft.apr}
                       onChange={(e) => setDraft((d) => ({ ...d, apr: e.target.value }))} />
              </Field>
            )}
            {isCredit && (
              <Field label="Credit Limit ($)">
                <input className="form-input" type="number" min="0" step="0.01"
                       value={draft.credit_limit}
                       onChange={(e) => setDraft((d) => ({ ...d, credit_limit: e.target.value }))} />
              </Field>
            )}
          </div>
          <div className="form-row-2">
            {isCredit && (
              <Field label="Minimum Payment ($)">
                <input className="form-input" type="number" min="0" step="0.01"
                       value={draft.minimum_payment}
                       onChange={(e) => setDraft((d) => ({ ...d, minimum_payment: e.target.value }))} />
              </Field>
            )}
            <Field label="Statement Day (1-31)">
              <input className="form-input" type="number" min="1" max="31"
                     value={draft.statement_day}
                     onChange={(e) => setDraft((d) => ({ ...d, statement_day: e.target.value }))} />
            </Field>
          </div>
          <div className="form-row-2">
            <Field label="Payment Due Day (1-31)">
              <input className="form-input" type="number" min="1" max="31"
                     value={draft.due_day}
                     onChange={(e) => setDraft((d) => ({ ...d, due_day: e.target.value }))} />
            </Field>
            <Field label="Notes">
              <input className="form-input" type="text"
                     value={draft.notes}
                     onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))} />
            </Field>
          </div>
          {err && <div style={{ color: '#f87171', fontSize: 13, marginTop: 4 }}>{err}</div>}
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-primary"
                    onClick={commit} disabled={saving}>
              {saving ? <><Spin /> Saving…</> : 'Save'}
            </button>
            <button type="button" className="btn btn-secondary"
                    onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

function DetailPill({ label, value }) {
  if (!value) {
    return (
      <span style={{ opacity: 0.5 }}>
        <strong>{label}:</strong> —
      </span>
    );
  }
  return (
    <span>
      <strong style={{ color: 'var(--text)' }}>{label}:</strong> {value}
    </span>
  );
}
