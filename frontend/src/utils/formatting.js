// Shared backend URL — avoids duplicating process.env access across every component.
export const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

export const fmt$ = (n) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(
        Math.abs(parseFloat(n) || 0)
    );

// Like fmt$, but preserves sign for values that can be negative (e.g. net worth).
// Round to cents before deciding the sign so values that *display* as $0.00
// (e.g. -0.003 from txn-derived rounding noise) don't render as "-$0.00".
export const fmtSigned = (n) => {
  const v = parseFloat(n) || 0;
  const cents = Math.round(v * 100);
  const abs = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(cents) / 100);
  return cents < 0 ? `-${abs}` : abs;
};

// Compact relative-time label for cache/sync timestamps. Accepts either an ISO
// string (`YYYY-MM-DDTHH:mm:ss`) or one without zone — naive strings are
// interpreted as UTC to match backend timestamps.
export function formatRelativeTime(isoString) {
  if (!isoString) return '';
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(isoString);
  const ts = new Date(hasZone ? isoString : isoString + 'Z').getTime();
  const diffMs = Date.now() - ts;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 2)   return 'just now';
  if (diffMin < 60)  return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24)   return `${diffHr}h ago`;
  return `${Math.round(diffHr / 24)}d ago`;
}

export const fmtDate = (s) => {
  const d = new Date(s + 'T00:00:00');
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

export const toYMD = (d) => d.toISOString().split('T')[0];

export function prevMonthRange() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0);
  return { from: toYMD(first), to: toYMD(last) };
}

export function thisMonthRange() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  return { from: toYMD(first), to: toYMD(now) };
}

export function channelLabel(source) {
  return source === 'simplefin' ? 'SimpleFIN' : 'CSV';
}

export const calculateHalf = (amount) =>
  parseFloat((Math.abs(parseFloat(amount)) / 2).toFixed(2));

export const formatAccountType = (type) => ({
  checking:        'Checking',
  savings:         'Savings',
  money_market:    'Money Market',
  credit_card:     'Credit Card',
  line_of_credit:  'Line of Credit',
  credit:          'Credit Card',
}[type] || type);

export const formatCategory = (cat) =>
  (cat || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

// Time-of-day greeting for the dashboard / Today banners. Shared so both
// pages address the user the same way at the same hour.
export function greetingFor(date) {
  const h = date.getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

// "August 15" — the banner date beside the greeting.
export function formatToday(date) {
  return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
}

export function txnMonthKey(dateStr) {
  if (!dateStr) return null;
  // ISO format (YYYY-MM-DD from SimpleFIN): append T00:00:00 so it's treated as local time, not UTC.
  // US format (MM/DD/YYYY from Discover/Barclays): pass directly — V8 parses it as local time already.
  const d = /^\d{4}-\d{2}-\d{2}/.test(dateStr)
    ? new Date(dateStr.slice(0, 10) + 'T00:00:00')
    : new Date(dateStr);
  if (isNaN(d)) return null;
  const key   = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  const label = d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  return { key, label };
}
