import { useCallback, useState } from 'react';

import { syncSimplefin } from '../api/simplefin';
import { syncSnapTrade } from '../api/snaptrade';

/**
 * The one "Sync all". Before this hook there were two, under the same label,
 * doing different things: the Accounts page refreshed the balances cache
 * without ever contacting the bank, while Settings ran the real pull. This
 * does the fuller thing everywhere.
 *
 * The two providers settle independently so a brokerage outage cannot mask a
 * successful bank sync, and the refresh runs regardless so a partial success
 * is never left showing stale numbers.
 */
export default function useSyncAll({ onRefresh }) {
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);

  const syncAll = useCallback(async () => {
    setSyncing(true);
    setSyncError(null);
    const results = await Promise.allSettled([syncSimplefin(), syncSnapTrade()]);
    const [bank, brokerage] = results;

    if (bank.status === 'rejected' && brokerage.status === 'rejected') {
      setSyncError('Sync failed — is the backend running?');
    } else if (brokerage.status === 'rejected') {
      setSyncError('Brokerages did not sync, but bank balances are up to date.');
    } else if (bank.status === 'rejected') {
      setSyncError('Banks did not sync, but brokerage holdings are up to date.');
    }

    try {
      await onRefresh?.();
    } finally {
      setSyncing(false);
    }
  }, [onRefresh]);

  return { syncAll, syncing, syncError };
}
