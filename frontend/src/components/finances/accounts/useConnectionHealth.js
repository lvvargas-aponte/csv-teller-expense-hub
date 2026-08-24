import { useMemo } from 'react';

// Per-institution connection state for the Accounts page.
//
// This used to ask SimpleFIN and SnapTrade directly on every mount, which made
// two aggregator round-trips the price of opening the tab. Health is now
// recorded when a sync runs and travels on the balances summary the page
// already loads, so viewing the page costs no provider call. The trade-off is
// deliberate: the strip reports health as of the last sync, alongside the
// "last sync <age>" label that dates it.
//
// Statuses: 'connected' | 'disconnected' | 'manual'.
export default function useConnectionHealth(connections) {
  return useMemo(() => {
    const institutions = connections ?? [];
    return {
      institutions,
      broken: institutions.filter((i) => i.status === 'disconnected'),
      connected: institutions.filter((i) => i.status === 'connected'),
    };
  }, [connections]);
}
