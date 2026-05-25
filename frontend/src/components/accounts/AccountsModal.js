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
  const [connecting,    setConnecting]    = useState(false);
  const [reconnecting,  setReconnecting]  = useState(null);  // account id being re-authenticated
  const [connectStatus, setConnectStatus] = useState(null);  // { type: 'success'|'error', message }
  const [tellerConfig,  setTellerConfig]  = useState(null);
  const [configError,   setConfigError]   = useState(null);

  const refreshAccounts = useCallback(() => {
    setLoading(true);
    setError(null);
    axios.get(`${API}/api/accounts`)
      .then((r) => setAccounts(r.data))
      .catch(() => setError('Could not load accounts — is the backend running?'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refreshAccounts(); }, [refreshAccounts]);

  useEffect(() => {
    axios.get(`${API}/api/config/teller`)
      .then((res) => setTellerConfig(res.data))
      .catch((e) => setConfigError(e.response?.data?.detail || e.message));
  }, []);

  const handleDisconnect = async (acctId) => {
    // Default disconnect: revokes the Teller token but keeps the local
    // record so transactions, last-known balance, and APR/limit details stay
    // around — a later reconnect of the same account picks them right back
    // up. The Linked Accounts list (this modal) only shows Teller-connected
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

  // Shared helper: open TellerConnect and call onSuccess with the enrollment object
  const openTellerConnect = ({ enrollmentId, onSuccess }) => {
    if (!tellerConfig) return;
    if (!window.TellerConnect) {
      setConnectStatus({ type: 'error', message: 'Teller SDK failed to load. Check your connection and reload.' });
      return;
    }

    const options = {
      applicationId: tellerConfig.application_id,
      environment:   tellerConfig.environment,
      onSuccess,
      onExit: () => {
        setConnecting(false);
        setReconnecting(null);
      },
    };
    if (enrollmentId) options.enrollmentId = enrollmentId;

    window.TellerConnect.setup(options).open();
  };

  const handleConnect = () => {
    setConnecting(true);
    setConnectStatus(null);

    openTellerConnect({
      onSuccess: async (enrollment) => {
        setConnecting(false);
        try {
          const res = await axios.post(`${API}/api/teller/register-token`, {
            access_token:  enrollment.accessToken,
            enrollment_id: enrollment.enrollment.id,
            institution:   enrollment.enrollment.institution.name,
          });
          const msg = res.data.registered === false
            ? 'This account was already connected.'
            : `${enrollment.enrollment.institution.name} connected!`;
          setConnectStatus({ type: 'success', message: msg });
          refreshAccounts();
        } catch (e) {
          setConnectStatus({ type: 'error', message: 'Failed to save token: ' + (e.response?.data?.detail || e.message) });
        }
      },
    });
  };

  const handleReconnect = (acct) => {
    setReconnecting(acct.id);
    setConnectStatus(null);

    openTellerConnect({
      // If we have the enrollment id, Teller Connect opens directly in re-auth mode
      enrollmentId: acct._enrollment_id || undefined,
      onSuccess: async (enrollment) => {
        setReconnecting(null);
        try {
          if (acct._enrollment_id) {
            // Known enrollment — swap out the broken token.  old_account_id
            // is a belt-and-suspenders so the dead token is still cleaned up
            // if the backend's in-memory enrollment map has been cleared.
            await axios.post(`${API}/api/teller/replace-token`, {
              old_enrollment_id: acct._enrollment_id,
              new_access_token:  enrollment.accessToken,
              new_enrollment_id: enrollment.enrollment.id,
              institution:       enrollment.enrollment.institution.name,
              old_account_id:    acct.id,
            });
          } else {
            // No stored enrollment id (e.g. after a backend restart) — register
            // as a fresh connection.  Passing old_account_id lets the backend
            // remove the broken token alongside the new one so the
            // "Connection Error" row doesn't linger.
            await axios.post(`${API}/api/teller/register-token`, {
              access_token:  enrollment.accessToken,
              enrollment_id: enrollment.enrollment.id,
              institution:   enrollment.enrollment.institution.name,
              old_account_id: acct.id,
            });
          }
          setConnectStatus({ type: 'success', message: `${enrollment.enrollment.institution.name} reconnected!` });
          refreshAccounts();
        } catch (e) {
          setConnectStatus({ type: 'error', message: 'Failed to update credentials: ' + (e.response?.data?.detail || e.message) });
        }
      },
    });
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
            const isReconnecting = reconnecting === acct.id;

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
                    <>
                      {!isRateLimited && (
                        <button
                          type="button"
                          className="btn btn-teller btn-sm"
                          aria-label={isReconnecting ? 'Reconnecting…' : 'Reconnect account'}
                          disabled={isReconnecting || !tellerConfig}
                          onClick={() => handleReconnect(acct)}
                        >
                          {isReconnecting ? <><Spin /> Reconnecting…</> : '↺'}
                        </button>
                      )}
                      <button type="button" className="btn btn-secondary btn-sm"
                              disabled={isDeleting}
                              onClick={() => setConfirming(acct.id)}>
                        {isDeleting ? <Spin /> : '🗑️'} Disconnect
                      </button>
                    </>
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

        <div className="modal-footer" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            {configError ? (
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                Bank connection unavailable: {configError}
              </span>
            ) : (
              <button
                type="button"
                className="btn btn-teller"
                onClick={handleConnect}
                disabled={connecting || !tellerConfig}
              >
                {connecting ? <><Spin /> Connecting…</> : '+ Connect a Bank'}
              </button>
            )}
          </div>
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
