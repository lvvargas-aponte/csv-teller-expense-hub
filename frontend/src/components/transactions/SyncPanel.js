import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../../utils/formatting';
import { chipColorFor } from '../../utils/institutionColor';

// Format the most recent sync time as e.g. "Last synced 2h ago".
function formatSinceLabel(lastSyncIso) {
  if (!lastSyncIso) return null;
  const last = new Date(lastSyncIso);
  if (isNaN(last)) return null;
  const mins = Math.max(0, Math.floor((Date.now() - last.getTime()) / 60000));
  if (mins < 1)    return 'Last synced just now';
  if (mins < 60)   return `Last synced ${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)    return `Last synced ${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `Last synced ${days}d ago`;
}

export default function SyncPanel({ onOpenAccounts, onOpenSync, syncing, refreshKey }) {
  const [accounts, setAccounts] = useState([]);

  const fetchAccounts = useCallback(() => {
    axios.get(`${API_BASE}/api/accounts`)
      .then((r) => setAccounts(Array.isArray(r.data) ? r.data : []))
      .catch(() => { /* SyncPanel is non-critical; failures are silent */ });
  }, []);

  useEffect(() => { fetchAccounts(); }, [fetchAccounts, refreshKey]);

  // De-dup: one chip per institution
  const institutions = [];
  const seen = new Set();
  for (const a of accounts) {
    const name = a.institution?.name;
    if (!name || seen.has(name)) continue;
    seen.add(name);
    institutions.push(name);
  }

  const lastSync = accounts
    .map((a) => a.last_sync || a.last_synced_at)
    .filter(Boolean)
    .sort()
    .pop();
  const sinceLabel = formatSinceLabel(lastSync);

  return (
    <div className="tx-sync-panel">
      <div className="tx-sync-accounts">
        {institutions.map((name) => {
          const c = chipColorFor(name);
          return (
            <button
              key={name}
              type="button"
              className="tx-account-chip"
              onClick={onOpenAccounts}
              title={`Manage ${name}`}
              style={{ borderColor: c.border, background: c.bg, color: c.color }}
            >
              <span className="tx-account-chip-dot" style={{ background: c.dot }} />
              {name}
            </button>
          );
        })}
        <button
          type="button"
          className="tx-account-chip tx-account-chip--add"
          onClick={onOpenAccounts}
          title="Add or manage accounts"
        >
          + Add
        </button>
      </div>
      {sinceLabel && <span className="tx-sync-meta">{sinceLabel}</span>}
      <button
        type="button"
        className="tx-sync-btn"
        onClick={onOpenSync}
        disabled={syncing}
      >
        <span className={syncing ? 'tx-spin' : ''} aria-hidden="true">⟳</span>
        <span>{syncing ? 'Syncing…' : 'Sync Banks'}</span>
      </button>
    </div>
  );
}
