import React, { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import SettingsCard from '../SettingsCard';
import AccountsModal from '../../accounts/AccountsModal';
import RemoveInstitutionDialog from '../RemoveInstitutionDialog';
import Spin from '../../ui/Spin';
import { API_BASE, formatRelativeTime } from '../../../utils/formatting';
import { syncSnapTrade } from '../../../api/snaptrade';

// Institutions the user maintains by hand have no connection to sync or
// repair — they get the off-state dot and a route into the accounts modal.
//
// `lastSynced` is the balances cache's single timestamp, not a per-row one:
// health is recorded per sync run, so every row is as fresh as the last run.
function InstitutionRow({ inst, accounts, lastSynced, onRemove }) {
  const broken = inst.status === 'disconnected';
  const manual = inst.status === 'manual';
  const names = accounts.map((a) => a.name).filter(Boolean);

  const dotClass = manual ? 'set-dot--off' : broken ? 'set-dot--warn' : 'set-dot--ok';

  return (
    <div
      className={`set-inst-row${broken ? ' set-inst-row--warn' : ''}`}
      role="group"
      aria-label={inst.institution}
    >
      <div className="set-inst-icon" aria-hidden="true">
        {manual ? '✎' : '🏦'}
      </div>
      <div className="set-inst-body">
        <div className="set-inst-name">{inst.institution}</div>
        <div className="set-inst-meta">
          <span className={`set-dot ${dotClass}`} aria-hidden="true" />
          {manual ? (
            <span>Not connected</span>
          ) : broken ? (
            <span className="set-inst-warn">Reconnect needed</span>
          ) : (
            <span>{lastSynced ? `Synced ${formatRelativeTime(lastSynced)}` : 'Synced'}</span>
          )}
          {names.length > 0 && (
            <>
              <span className="set-inst-sep" aria-hidden="true">·</span>
              <span>
                {names.length} account{names.length === 1 ? '' : 's'}: {names.join(', ')}
              </span>
            </>
          )}
        </div>
        {broken && (
          <div className="set-inst-fix">
            {inst.last_error ? `${inst.last_error} — ` : ''}
            Reconnecting happens at your SimpleFIN Bridge account: sign in
            there, re-authorize {inst.institution}, then sync again here.
          </div>
        )}
      </div>
      <div className="set-inst-actions">
        <button type="button" className="set-inst-remove" onClick={onRemove}>
          Remove
        </button>
      </div>
    </div>
  );
}

export default function ConnectionsPane({ health, summary, onRefresh }) {
  const { institutions = [], broken = [] } = health || {};
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);
  const [showConnect, setShowConnect] = useState(false);
  const [removing, setRemoving] = useState(null);      // institution name
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState(null);

  const accountsByInstitution = useMemo(() => {
    const map = new Map();
    for (const a of summary?.accounts || []) {
      const key = a.institution || '—';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(a);
    }
    return map;
  }, [summary]);

  const connected = institutions.filter((i) => i.status !== 'manual');
  const manual    = institutions.filter((i) => i.status === 'manual');

  const syncAll = useCallback(async () => {
    setSyncing(true);
    setSyncError(null);
    // SnapTrade failing shouldn't hide a successful bank sync, so the two
    // providers are settled independently.
    const results = await Promise.allSettled([
      axios.post(`${API_BASE}/api/simplefin/sync`, {}),
      syncSnapTrade(),
    ]);
    const failed = results.filter((r) => r.status === 'rejected');
    if (failed.length === results.length) {
      setSyncError('Sync failed — is the backend running?');
    } else if (failed.length) {
      setSyncError('Brokerages did not sync, but bank balances are up to date.');
    }
    setSyncing(false);
    onRefresh?.();
  }, [onRefresh]);

  // No institution-level revoke exists server-side, so this detaches each
  // account in turn. The default (no ?purge) keeps the local record and the
  // transaction history — see RemoveInstitutionDialog.
  const confirmRemove = useCallback(async () => {
    const targets = accountsByInstitution.get(removing) || [];
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      for (const acct of targets) {
        await axios.delete(`${API_BASE}/api/accounts/${encodeURIComponent(acct.id)}`);
      }
      setRemoving(null);
      onRefresh?.();
    } catch {
      setRemoveError('Could not remove every account — some may still be connected.');
    } finally {
      setRemoveBusy(false);
    }
  }, [removing, accountsByInstitution, onRefresh]);

  const desc = institutions.length === 0
    ? 'No banks connected yet.'
    : `${connected.length} bank${connected.length === 1 ? '' : 's'} connected, `
      + (broken.length
        ? `${broken.length} need${broken.length === 1 ? 's' : ''} attention`
        : 'all healthy');

  return (
    <>
      <div className="set-pane-head">
        <h2 className="set-pane-title">Connected institutions</h2>
        <p className="set-pane-desc">
          {desc}. Balances refresh automatically once a day; a connection
          breaks when the bank asks you to log in again.
        </p>
      </div>

      {syncError && <div className="set-inline-error">{syncError}</div>}

      <SettingsCard
        title="Connected"
        hint="syncs daily"
        action={(
          <button
            type="button" className="btn btn-secondary btn-sm"
            onClick={syncAll} disabled={syncing}
          >
            {syncing ? <><Spin /> Syncing…</> : '⟳ Sync all'}
          </button>
        )}
        flush
      >
        {connected.length === 0 ? (
          <div className="set-empty">No connected institutions yet.</div>
        ) : connected.map((inst) => (
          <InstitutionRow
            key={inst.institution}
            inst={inst}
            accounts={accountsByInstitution.get(inst.institution) || []}
            lastSynced={summary?.cache_fetched_at}
            onRemove={() => { setRemoving(inst.institution); setRemoveError(null); }}
          />
        ))}
        <button
          type="button"
          className="set-inst-add"
          onClick={() => setShowConnect(true)}
        >
          + Connect a bank or card
        </button>
      </SettingsCard>

      {manual.length > 0 && (
        <SettingsCard
          title="Manual accounts"
          hint="you keep these up to date yourself"
          flush
        >
          {manual.map((inst) => (
            <InstitutionRow
              key={inst.institution}
              inst={inst}
              accounts={accountsByInstitution.get(inst.institution) || []}
            />
          ))}
        </SettingsCard>
      )}

      {showConnect && (
        <AccountsModal onClose={() => { setShowConnect(false); onRefresh?.(); }} />
      )}

      {removing && (
        <RemoveInstitutionDialog
          institution={removing}
          accounts={accountsByInstitution.get(removing) || []}
          busy={removeBusy}
          error={removeError}
          onConfirm={confirmRemove}
          onCancel={() => setRemoving(null)}
        />
      )}
    </>
  );
}
