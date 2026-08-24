import React, { useState } from 'react';
import AccountsModal from '../../accounts/AccountsModal';
import { formatRelativeTime } from '../../../utils/formatting';

// One-line connection health summary, replacing the per-institution chip row
// and the per-account sync chips. Sync failures surface here rather than on
// individual rows.
//
// `health` comes from useConnectionHealth, owned by the parent so the rows can
// mark the same broken institutions without a second round of requests.
export default function ConnectionsStrip({
  health,
  cacheFetchedAt,
  syncError,
  onRefresh,
  onManageConnections,
}) {
  const { institutions = [], broken = [], connected = [] } = health || {};
  const [showManage, setShowManage] = useState(false);

  // Managing connections lives on the settings page. Falls back to the
  // modal when rendered without that route (standalone, tests).
  const manage = onManageConnections || (() => setShowManage(true));

  const closeManage = () => {
    setShowManage(false);
    onRefresh?.();
  };

  const attention = !!syncError || broken.length > 0;
  const lastSync = cacheFetchedAt ? formatRelativeTime(cacheFetchedAt) : null;
  const healthyCount = connected.length || institutions.length;

  return (
    <>
      <div className={`acct-conn${attention ? ' acct-conn--attention' : ''}`}>
        <span className={`acct-conn-dot${attention ? ' acct-conn-dot--warn' : ''}`} />
        <span className="acct-conn-text" title={broken[0]?.last_error || undefined}>
          {syncError ? (
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
            onClick={manage}
          >
            Reconnect
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          onClick={manage}
        >
          {institutions.length === 0 ? '+ Connect bank' : 'Manage connections'}
        </button>
      </div>

      {showManage && <AccountsModal onClose={closeManage} />}
    </>
  );
}
