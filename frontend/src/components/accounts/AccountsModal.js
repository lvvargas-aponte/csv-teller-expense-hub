import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Backdrop from '../ui/Backdrop';
import Spin from '../ui/Spin';
import { formatAccountType } from '../../utils/formatting';
import { Z_BACKDROP_PANEL } from '../../utils/zIndex';

const API = process.env.REACT_APP_BACKEND_URL || '';
const PURGE_CONFIRM_WORD = 'delete';

export default function AccountsModal({ onClose }) {
  const [accounts,      setAccounts]      = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState(null);
  const [confirming,    setConfirming]    = useState(null);  // account id pending disconnect confirm
  const [purging,       setPurging]       = useState(null);  // account being permanently deleted: { id, label }
  const [purgeText,     setPurgeText]     = useState('');    // what the user has typed so far
  const [deleting,      setDeleting]      = useState(null);  // account id whose DELETE call is in flight
  const [connectStatus, setConnectStatus] = useState(null);  // { type: 'success'|'error', message }
  const [simplefinToken,    setSimplefinToken]    = useState('');
  const [claimingSimplefin, setClaimingSimplefin] = useState(false);

  const refreshAccounts = useCallback(() => {
    setLoading(true);
    setError(null);
    axios.get(`${API}/api/accounts`)
      .then((r) => setAccounts(r.data))
      .catch(() => setError('Could not load accounts — is the backend running?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refreshAccounts(); }, [refreshAccounts]);

  const handleDisconnect = async (acctId) => {
    // Default disconnect: revokes the connection but keeps the local
    // record so transactions, last-known balance, and APR/limit details stay
    // around — a later reconnect of the same account picks them right back
    // up. The Linked Accounts list (this modal) only shows connected
    // rows, so the row disappears here after the call succeeds.
    setDeleting(acctId);
    setConfirming(null);
    try {
      await axios.delete(`${API}/api/accounts/${acctId}`);
      setAccounts((prev) => prev.filter((a) => a.id !== acctId));
    } catch (e) {
      setError('Could not disconnect account: ' + (e.response?.data?.detail || e.message));
    } finally {
      setDeleting(null);
    }
  };

  const handlePurge = async () => {
    if (!purging || purgeText.trim().toLowerCase() !== PURGE_CONFIRM_WORD) return;
    const acctId = purging.id;
    setDeleting(acctId);
    try {
      await axios.delete(`${API}/api/accounts/${acctId}`, { params: { purge: true } });
      setAccounts((prev) => prev.filter((a) => a.id !== acctId));
      setPurging(null);
      setPurgeText('');
    } catch (e) {
      setError('Could not delete account: ' + (e.response?.data?.detail || e.message));
    } finally {
      setDeleting(null);
    }
  };

  const handleClaimSimplefin = async () => {
    const token = simplefinToken.trim();
    if (!token) return;
    setClaimingSimplefin(true);
    setConnectStatus(null);
    try {
      const res = await axios.post(`${API}/api/simplefin/claim`, { setup_token: token });
      const msg = res.data.claimed === false
        ? 'This SimpleFIN connection was already added.'
        : 'SimpleFIN connected! Its accounts will appear after your next Sync.';
      setConnectStatus({ type: 'success', message: msg });
      setSimplefinToken('');
      refreshAccounts();
    } catch (e) {
      setConnectStatus({ type: 'error', message: 'Failed to connect SimpleFIN: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setClaimingSimplefin(false);
    }
  };

  return (
    <Backdrop onClose={onClose} zIndex={Z_BACKDROP_PANEL}>
      <div className="modal modal--sm">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Linked Bank Accounts</div>
            <div className="modal-sub">Connect new accounts or disconnect ones you no longer use</div>
          </div>
          <button type="button" className="close-btn" aria-label="Close accounts panel" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading && <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin /> Loading…</div>}
          {error   && <div style={{ color: '#f87171', fontSize: 14 }}>{error}</div>}

          {!loading && !error && accounts.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>No linked accounts found.</div>
          )}

          {accounts.map((acct) => {
            const institution  = acct.institution?.name || '—';
            const subtype      = formatAccountType(acct.subtype || acct.type || '');
            const isConfirming = confirming    === acct.id;
            const isDeleting   = deleting      === acct.id;

            const isRateLimited = acct._connection_error && acct._error_status === 429;

            const statusChip = acct._connection_error
              ? isRateLimited
                ? { label: 'Rate Limited', bg: '#422006', color: '#fbbf24' }
                : { label: 'Connection Error', bg: '#450a0a', color: '#fca5a5' }
              : acct.status === 'closed'
                ? { label: 'Closed',  bg: '#1f2937', color: '#9ca3af' }
                : { label: 'Active',  bg: '#052e16', color: '#86efac' };

            return (
              <div key={acct.id} className="account-row">
                <div className="account-row-info">
                  <div className="account-row-name" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {institution}
                    <span style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: '2px 7px',
                      borderRadius: 4,
                      background: statusChip.bg,
                      color: statusChip.color,
                      letterSpacing: '0.02em',
                    }}>
                      {statusChip.label}
                    </span>
                  </div>
                  <div className="account-row-sub">{acct.name} · {subtype}</div>
                </div>

                <div className="account-row-actions">
                  {acct._connection_error && !isConfirming ? (
                    <button type="button" className="btn btn-secondary btn-sm"
                            disabled={isDeleting}
                            onClick={() => setConfirming(acct.id)}>
                      {isDeleting ? <Spin /> : '🗑️'} Disconnect
                    </button>
                  ) : isConfirming ? (
                    <>
                      <span className="account-row-confirm-label">Disconnect? Local data stays.</span>
                      <button type="button" className="btn btn-sm"
                              style={{ background: '#ef4444', color: '#fff' }}
                              onClick={() => handleDisconnect(acct.id)}>
                        Yes
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm"
                              onClick={() => setConfirming(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn btn-secondary btn-sm"
                              disabled={isDeleting}
                              onClick={() => setConfirming(acct.id)}>
                        {isDeleting ? <Spin /> : '🗑️'} Disconnect
                      </button>
                      <button type="button" className="btn btn-sm"
                              style={{ background: 'transparent', color: '#f87171', border: '1px solid #f87171' }}
                              disabled={isDeleting}
                              title="Permanently delete this account and all its local data"
                              onClick={() => {
                                setPurging({ id: acct.id, label: `${institution} · ${acct.name}` });
                                setPurgeText('');
                              }}>
                        Delete permanently
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}

          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border, #334155)' }}>
            <div className="field-label" style={{ marginBottom: 6 }}>Connect via SimpleFIN</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              Visit <a href="https://bridge.simplefin.org/simplefin/create" target="_blank" rel="noopener noreferrer">
                bridge.simplefin.org
              </a>, connect a bank, and paste the Setup Token it gives you below.
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={simplefinToken}
                onChange={(e) => setSimplefinToken(e.target.value)}
                placeholder="Paste Setup Token"
                disabled={claimingSimplefin}
                className="form-input"
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={claimingSimplefin || !simplefinToken.trim()}
                onClick={handleClaimSimplefin}
              >
                {claimingSimplefin ? <><Spin /> Connecting…</> : 'Connect'}
              </button>
            </div>
          </div>

          {connectStatus && (
            <div style={{
              marginTop: 16,
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: 13,
              background: connectStatus.type === 'success' ? '#064e3b' : '#450a0a',
              color:      connectStatus.type === 'success' ? '#6ee7b7' : '#fca5a5',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
            }}>
              <span>{connectStatus.type === 'success' ? '✓ ' : '✕ '}{connectStatus.message}</span>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setConnectStatus(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0, fontSize: 16, lineHeight: 1 }}
              >
                ✕
              </button>
            </div>
          )}
        </div>

        <div className="modal-footer" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>

      {purging && (() => {
        const matches = purgeText.trim().toLowerCase() === PURGE_CONFIRM_WORD;
        const isBusy  = deleting === purging.id;
        return (
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Confirm permanent account deletion"
            style={{
              position: 'fixed', inset: 0, zIndex: Z_BACKDROP_PANEL + 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(0,0,0,0.55)',
            }}
            onClick={(e) => {
              if (e.target === e.currentTarget && !isBusy) {
                setPurging(null);
                setPurgeText('');
              }
            }}
          >
            <div className="modal modal--sm" style={{ maxWidth: 460 }}>
              <div className="modal-header">
                <div className="modal-header-text">
                  <div className="modal-title">Delete account permanently?</div>
                  <div className="modal-sub">{purging.label}</div>
                </div>
              </div>
              <div className="modal-body" style={{ fontSize: 14, lineHeight: 1.5 }}>
                <p style={{ marginTop: 0 }}>
                  This will remove the account everywhere — its balance, snapshots,
                  and APR / credit-limit details. Linked transactions stay but lose
                  their account reference.
                </p>
                <p>
                  To confirm, type <code style={{ background: '#1f2937', padding: '1px 6px', borderRadius: 4 }}>{PURGE_CONFIRM_WORD}</code> below.
                </p>
                <label htmlFor="purge-confirm" className="sr-only">Type delete to confirm</label>
                <input
                  id="purge-confirm"
                  type="text"
                  autoFocus
                  value={purgeText}
                  onChange={(e) => setPurgeText(e.target.value)}
                  placeholder={PURGE_CONFIRM_WORD}
                  disabled={isBusy}
                  style={{
                    width: '100%', padding: '8px 10px', marginTop: 4,
                    background: '#0f172a', color: '#e5e7eb',
                    border: '1px solid #334155', borderRadius: 6, fontSize: 14,
                  }}
                />
              </div>
              <div className="modal-footer" style={{ justifyContent: 'flex-end', gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={isBusy}
                  onClick={() => { setPurging(null); setPurgeText(''); }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  style={{
                    background: matches ? '#ef4444' : '#7f1d1d',
                    color: '#fff',
                    opacity: matches ? 1 : 0.6,
                    cursor: matches && !isBusy ? 'pointer' : 'not-allowed',
                  }}
                  disabled={!matches || isBusy}
                  onClick={handlePurge}
                >
                  {isBusy ? <><Spin /> Deleting…</> : 'Delete forever'}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </Backdrop>
  );
}
