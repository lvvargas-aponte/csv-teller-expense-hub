import React from 'react';
import { formatRelativeTime } from '../../../utils/formatting';

// 24h freshness threshold — over a day old means we should warn the user that
// what they see may not reflect bank reality.
const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

// Per-account sync chip. Manual accounts get a Manual badge instead of a chip.
// Connected accounts derive live/stale from the global cache_fetched_at since
// the backend doesn't track last_synced_at per account.
export default function SyncChip({ manual, cacheFetchedAt }) {
  if (manual) {
    return <span className="manual-badge">Manual</span>;
  }
  if (!cacheFetchedAt) return null;

  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(cacheFetchedAt);
  const ts = new Date(hasZone ? cacheFetchedAt : cacheFetchedAt + 'Z').getTime();
  const stale = Date.now() - ts > STALE_AFTER_MS;
  const cls = stale ? 'sync-chip sync-chip--stale' : 'sync-chip sync-chip--live';
  const label = formatRelativeTime(cacheFetchedAt);

  return (
    <span className={cls} title={`Last synced ${label}`}>
      <span className="sync-dot" />
      {label}
    </span>
  );
}
