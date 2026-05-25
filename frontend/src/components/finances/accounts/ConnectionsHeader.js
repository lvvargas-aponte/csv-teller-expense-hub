import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { API_BASE } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';
import AccountsModal from '../../accounts/AccountsModal';

// Header for the Accounts tab — one chip per institution showing its
// connection state. Mirrors the Transactions page's SyncPanel pattern, but
// also surfaces manual-only and disconnected (error) institutions.
//
// `summaryAccounts` is the merged list from /api/balances/summary (manual +
// Teller-cached). We additionally fetch /api/accounts so we can detect
// `_connection_error` rows that the cached summary doesn't carry.
export default function ConnectionsHeader({ summaryAccounts = [], onRefresh }) {
  const [tellerAccounts, setTellerAccounts] = useState([]);
  const [showManage, setShowManage] = useState(false);

  useEffect(() => {
    axios.get(`${API_BASE}/api/accounts`)
      .then((r) => setTellerAccounts(Array.isArray(r.data) ? r.data : []))
      .catch(() => { /* non-critical header */ });
  }, []);

  // Build one entry per institution with a connection status:
  //   'connected'    → at least one healthy Teller account
  //   'disconnected' → has Teller account(s) but all are in error
  //   'manual'       → only manual accounts for this institution
  const institutions = useMemo(() => {
    const byName = new Map();

    for (const a of tellerAccounts) {
      const name = a.institution?.name;
      if (!name) continue;
      const cur = byName.get(name) ?? { name, status: 'disconnected', hasError: false };
      if (a._connection_error) cur.hasError = true;
      else cur.status = 'connected';
      byName.set(name, cur);
    }

    for (const a of summaryAccounts) {
      const name = a.institution;
      if (!name) continue;
      if (a.manual) {
        if (!byName.has(name)) {
          byName.set(name, { name, status: 'manual', hasError: false });
        }
      } else if (!byName.has(name)) {
        // A Teller-cached account whose token is missing from /api/accounts
        // (e.g. backend restart with empty token list). Surface as disconnected.
        byName.set(name, { name, status: 'disconnected', hasError: true });
      }
    }

    return Array.from(byName.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [tellerAccounts, summaryAccounts]);

  const closeManage = () => {
    setShowManage(false);
    onRefresh?.();
  };

  return (
    <>
      <div className="tx-sync-panel" style={{ marginBottom: 16 }}>
        <div className="tx-sync-accounts">
          {institutions.length === 0 ? (
            <span style={{ fontSize: 12, color: '#6b7280' }}>
              No banks connected yet.
            </span>
          ) : institutions.map((inst) => {
            const c = chipColorFor(inst.name);
            const isConnected    = inst.status === 'connected';
            const isManual       = inst.status === 'manual';
            const isDisconnected = inst.status === 'disconnected';

            const style = isConnected
              ? { borderColor: c.border, background: c.bg, color: c.color }
              : isManual
                ? { borderColor: 'var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }
                : { borderColor: '#fecaca', background: 'var(--red-light)', color: '#b91c1c' };

            const dotColor = isConnected ? c.dot
              : isManual ? '#9ca3af'
                : '#dc2626';

            const title = isConnected ? `${inst.name} — connected via Teller`
              : isManual ? `${inst.name} — manual entry (not connected to Teller)`
                : `${inst.name} — connection error, click to reconnect`;

            const suffix = isManual ? ' · Manual'
              : isDisconnected ? ' · Reconnect'
                : '';

            return (
              <button
                key={inst.name}
                type="button"
                className="tx-account-chip"
                onClick={() => setShowManage(true)}
                title={title}
                style={style}
              >
                <span className="tx-account-chip-dot" style={{ background: dotColor }} />
                {inst.name}{suffix}
              </button>
            );
          })}
          <button
            type="button"
            className="tx-account-chip tx-account-chip--add"
            onClick={() => setShowManage(true)}
            title="Connect or manage banks"
          >
            + Connect bank
          </button>
        </div>
      </div>

      {showManage && <AccountsModal onClose={closeManage} />}
    </>
  );
}
