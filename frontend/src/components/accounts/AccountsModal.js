import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Backdrop from '../ui/Backdrop';
import Spin from '../ui/Spin';
import { Z_BACKDROP_PANEL } from '../../utils/zIndex';
import AccountRow from './AccountRow';
import BrokerageRow from './BrokerageRow';
import SimplefinConnectForm from './SimplefinConnectForm';
import PurgeConfirmDialog, { PURGE_CONFIRM_WORD } from './PurgeConfirmDialog';
import { listSnapTradeConnections, removeSnapTradeConnection } from '../../api/snaptrade';
import { getBalancesSummary } from '../../api/balances';
import { listAccounts, disconnectAccount, purgeAccount } from '../../api/accounts';
import { userMessage } from '../../utils/errorMessage';

/**
 * Errors first (they need action), then one group per institution, then
 * manually-added accounts. Institutions keep the order the API returned them
 * in so the list doesn't reshuffle between fetches.
 */
function groupAccounts(accounts) {
  const errors = [];
  const manual = [];
  const byInstitution = new Map();

  for (const acct of accounts) {
    if (acct._connection_error) {
      errors.push(acct);
    } else if (acct._source === 'manual') {
      manual.push(acct);
    } else {
      const name = acct.institution?.name || '—';
      if (!byInstitution.has(name)) byInstitution.set(name, []);
      byInstitution.get(name).push(acct);
    }
  }

  return [
    ...(errors.length ? [{ key: '_errors', label: 'Needs attention', accounts: errors }] : []),
    ...[...byInstitution].map(([label, rows]) => ({ key: label, label, accounts: rows })),
    ...(manual.length ? [{ key: '_manual', label: 'Added manually', accounts: manual }] : []),
  ];
}

export default function AccountsModal({ onClose }) {
  const [accounts,   setAccounts]   = useState([]);
  const [brokerages, setBrokerages] = useState([]);
  const [brokerageAccounts, setBrokerageAccounts] = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);
  const [confirming, setConfirming] = useState(null);  // id pending disconnect confirm
  const [purging,    setPurging]    = useState(null);  // { id, label } pending permanent delete
  const [deleting,   setDeleting]   = useState(null);  // id whose DELETE is in flight

  const refreshAccounts = useCallback(() => {
    setLoading(true);
    setError(null);
    listAccounts()
      .then((r) => setAccounts(r.data))
      .catch(() => setError('Could not load accounts — is the backend running?'))
      .finally(() => setLoading(false));
  }, []);

  // SnapTrade is optional and independently configured, so its failures stay
  // silent — a missing brokerage list must not blank out the bank rows.
  const refreshBrokerages = useCallback(() => {
    listSnapTradeConnections()
      .then((r) => setBrokerages(r.data?.connections || []))
      .catch(() => setBrokerages([]));
    getBalancesSummary(false)
      .then((r) => setBrokerageAccounts(
        (r.data?.accounts || []).filter((a) => a.source === 'snaptrade'),
      ))
      .catch(() => setBrokerageAccounts([]));
  }, []);

  useEffect(() => { refreshAccounts(); refreshBrokerages(); }, [refreshAccounts, refreshBrokerages]);

  const groups = useMemo(() => groupAccounts(accounts), [accounts]);
  const hasSimplefin = useMemo(
    () => accounts.some((a) => a._source === 'simplefin'),
    [accounts],
  );

  const handleDisconnect = useCallback(async (acctId) => {
    // Default disconnect keeps the local record so transactions, last-known
    // balance, and APR/limit details survive a later reconnect. This list
    // shows only connected rows, so the row disappears once it succeeds.
    setDeleting(acctId);
    setConfirming(null);
    try {
      await disconnectAccount(acctId);
      setAccounts((prev) => prev.filter((a) => a.id !== acctId));
    } catch (e) {
      setError(userMessage(e, 'Could not disconnect the account — please try again.'));
    } finally {
      setDeleting(null);
    }
  }, []);

  const handleBrokerageDisconnect = useCallback(async (connId) => {
    setDeleting(connId);
    setConfirming(null);
    try {
      await removeSnapTradeConnection(connId);
      setBrokerages((prev) => prev.filter((c) => c.id !== connId));
      refreshBrokerages();
    } catch (e) {
      setError(userMessage(e, 'Could not disconnect the brokerage — please try again.'));
    } finally {
      setDeleting(null);
    }
  }, [refreshBrokerages]);

  const handlePurge = useCallback(async () => {
    const acctId = purging.id;
    setDeleting(acctId);
    try {
      await purgeAccount(acctId);
      setAccounts((prev) => prev.filter((a) => a.id !== acctId));
      setPurging(null);
    } catch (e) {
      setError(userMessage(e, 'Could not delete the account — please try again.'));
    } finally {
      setDeleting(null);
    }
  }, [purging]);

  return (
    <Backdrop onClose={onClose} zIndex={Z_BACKDROP_PANEL}>
      <div className="modal modal--lg modal--scroll-body">
        <div className="modal-header">
          <div className="modal-header-text">
            <div className="modal-title">Linked Accounts</div>
            <div className="modal-sub">Connect banks and brokerages, or disconnect ones you no longer use</div>
          </div>
          <button type="button" className="close-btn" aria-label="Close accounts panel" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading && <div className="account-modal-loading"><Spin /> Loading…</div>}
          {error   && <div className="account-modal-error">{error}</div>}

          {!loading && !error && accounts.length === 0 && brokerages.length === 0 && (
            <div className="account-modal-empty">No linked accounts found.</div>
          )}

          {groups.map((group) => (
            <div key={group.key} className="account-group" role="group" aria-label={group.label}>
              <div className="account-group-label" data-testid="account-group-label">
                <span>{group.label}</span>
                <span className="account-group-count">{group.accounts.length}</span>
              </div>
              {group.accounts.map((acct) => (
                <AccountRow
                  key={acct.id}
                  acct={acct}
                  institution={acct.institution?.name || '—'}
                  isConfirming={confirming === acct.id}
                  isDeleting={deleting === acct.id}
                  onConfirm={setConfirming}
                  onCancelConfirm={() => setConfirming(null)}
                  onDisconnect={handleDisconnect}
                  onPurge={setPurging}
                />
              ))}
            </div>
          ))}

          {brokerages.length > 0 && (
            <div className="account-group" role="group" aria-label="Brokerages">
              <div className="account-group-label" data-testid="account-group-label">
                <span>Brokerages</span>
                <span className="account-group-count">{brokerages.length}</span>
              </div>
              {brokerages.map((conn) => (
                <BrokerageRow
                  key={conn.id}
                  conn={conn}
                  accountCount={brokerageAccounts.filter(
                    (a) => a.institution === conn.brokerage,
                  ).length}
                  isConfirming={confirming === conn.id}
                  isDeleting={deleting === conn.id}
                  onConfirm={setConfirming}
                  onCancelConfirm={() => setConfirming(null)}
                  onDisconnect={handleBrokerageDisconnect}
                />
              ))}
            </div>
          )}
        </div>

        <div className="modal-footer account-modal-footer">
          {!loading && <SimplefinConnectForm collapsible={hasSimplefin} onClaimed={refreshAccounts} />}
          <button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>

      {purging && (
        <PurgeConfirmDialog
          target={purging}
          busy={deleting === purging.id}
          onCancel={() => setPurging(null)}
          onConfirm={handlePurge}
        />
      )}
    </Backdrop>
  );
}

export { PURGE_CONFIRM_WORD };
