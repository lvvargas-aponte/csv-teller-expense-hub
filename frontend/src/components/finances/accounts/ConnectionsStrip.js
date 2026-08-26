import React, { useCallback, useMemo, useState } from 'react';
import AccountsModal from '../../accounts/AccountsModal';
import RemoveInstitutionDialog from '../../settings/RemoveInstitutionDialog';
import { formatRelativeTime } from '../../../utils/formatting';
import { disconnectAccount } from '../../../api/accounts';

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

// One-line connection health summary, with the full per-institution list
// (status, accounts, removal) expandable underneath. This is the single
// place connections are managed — it used to be split between this strip
// and a Settings pane, each with its own idea of "Sync all".
//
// `health` comes from useConnectionHealth, owned by the parent so the rows can
// mark the same broken institutions without a second round of requests.
export default function ConnectionsStrip({
  health,
  summary,
  cacheFetchedAt,
  syncing,
  syncError,
  onRefresh,
}) {
  const { institutions = [], broken = [] } = health || {};
  const [expanded, setExpanded] = useState(false);
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
  const manual = institutions.filter((i) => i.status === 'manual');

  // No institution-level revoke exists server-side, so this detaches each
  // account in turn. The default (no ?purge) keeps the local record and the
  // transaction history — see RemoveInstitutionDialog.
  const confirmRemove = useCallback(async () => {
    const targets = accountsByInstitution.get(removing) || [];
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      for (const acct of targets) {
        await disconnectAccount(acct.id);
      }
      setRemoving(null);
      onRefresh?.();
    } catch {
      setRemoveError('Could not remove every account — some may still be connected.');
    } finally {
      setRemoveBusy(false);
    }
  }, [removing, accountsByInstitution, onRefresh]);

  const attention = !!syncError || broken.length > 0;
  const lastSync = cacheFetchedAt ? formatRelativeTime(cacheFetchedAt) : null;
  const healthyCount = health?.connected?.length || institutions.length;

  return (
    <>
      <div className={`acct-conn${attention ? ' acct-conn--attention' : ''}`}>
        <span className={`acct-conn-dot${attention ? ' acct-conn-dot--warn' : ''}`} />
        <span className="acct-conn-text" title={broken[0]?.last_error || undefined}>
          {syncing ? (
            <>Syncing…</>
          ) : syncError ? (
            <>Sync failed — {syncError}</>
          ) : broken.length > 0 ? (
            <>
              <strong>{broken[0].institution}</strong>
              {broken.length > 1 && ` and ${broken.length - 1} other${broken.length > 2 ? 's' : ''}`}
              {broken.length === 1 ? ' needs' : ' need'} to be reconnected
              {lastSync ? ` — last synced ${lastSync}.` : '.'}
            </>
          ) : institutions.length === 0 ? (
            <>No banks connected yet.</>
          ) : (
            <>
              <strong>
                All {healthyCount} connection{healthyCount === 1 ? '' : 's'} healthy.
              </strong>
              {lastSync ? ` Last sync ${lastSync}.` : ''}
            </>
          )}
        </span>
        <span className="acct-conn-spacer" />
        {broken.length > 0 && (
          <button
            type="button"
            className="btn btn-warn"
            onClick={() => setExpanded(true)}
          >
            Reconnect
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setExpanded((v) => !v)}
        >
          {institutions.length === 0 ? '+ Connect bank' : 'Manage connections'}
        </button>
      </div>

      {expanded && (
        <div className="set-card">
          <div className="set-card-body set-card-body--flush">
            {connected.length === 0 ? (
              <div className="set-empty">No connected institutions yet.</div>
            ) : connected.map((inst) => (
              <InstitutionRow
                key={inst.institution}
                inst={inst}
                accounts={accountsByInstitution.get(inst.institution) || []}
                lastSynced={cacheFetchedAt}
                onRemove={() => { setRemoving(inst.institution); setRemoveError(null); }}
              />
            ))}
            {manual.map((inst) => (
              <InstitutionRow
                key={inst.institution}
                inst={inst}
                accounts={accountsByInstitution.get(inst.institution) || []}
              />
            ))}
            <button
              type="button"
              className="set-inst-add"
              onClick={() => setShowConnect(true)}
            >
              + Connect a bank or card
            </button>
          </div>
        </div>
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
