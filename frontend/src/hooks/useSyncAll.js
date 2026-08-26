import { useCallback, useState } from 'react';

import { syncSimplefin } from '../api/simplefin';
import { syncSnapTrade } from '../api/snaptrade';

// A configured-but-unconnected brokerage (409) or an unconfigured one (503)
// is not a sync failure — it's "not applicable to this user" — so it must
// not be reported as one even when hasBrokerages led us to try it.
function isBrokerageNotApplicable(reason) {
  const status = reason?.response?.status;
  return status === 503 || status === 409;
}

/**
 * The one "Sync all". Before this hook there were two, under the same label,
 * doing different things: the Accounts page refreshed the balances cache
 * without ever contacting the bank, while Settings ran the real pull. This
 * does the fuller thing everywhere.
 *
 * The two providers settle independently so a brokerage outage cannot mask a
 * successful bank sync, and the refresh runs regardless so a partial success
 * is never left showing stale numbers.
 *
 * `hasBrokerages` gates whether SnapTrade is worth calling at all. Most
 * users are SimpleFIN-only: POST /api/snaptrade/sync answers 503 when
 * SnapTrade isn't configured and 409 when it's configured but unconnected,
 * so calling it unconditionally reported a "failure" on every successful
 * sync for the common case. When false, SnapTrade is skipped entirely
 * rather than called and its rejection ignored.
 */
export default function useSyncAll({ onRefresh, hasBrokerages = false }) {
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);

  const syncAll = useCallback(async () => {
    setSyncing(true);
    setSyncError(null);
    const results = await Promise.allSettled([
      syncSimplefin(),
      hasBrokerages ? syncSnapTrade() : Promise.resolve({ skipped: true }),
    ]);
    const [bank, brokerage] = results;
    const brokerageFailed = brokerage.status === 'rejected'
      && !isBrokerageNotApplicable(brokerage.reason);

    if (bank.status === 'rejected' && brokerageFailed) {
      setSyncError('Sync failed — is the backend running?');
    } else if (brokerageFailed) {
      setSyncError('Brokerages did not sync, but bank balances are up to date.');
    } else if (bank.status === 'rejected') {
      setSyncError('Banks did not sync, but brokerage holdings are up to date.');
    }

    try {
      await onRefresh?.();
    } finally {
      setSyncing(false);
    }
  }, [onRefresh, hasBrokerages]);

  return { syncAll, syncing, syncError };
}
