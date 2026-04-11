export const fmt$ = (n) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(
        Math.abs(parseFloat(n) || 0)
    );

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
  return source === 'teller' ? 'Teller' : 'CSV';
}

export const CHANNEL_COLOR = {
  Teller: '#10b981',  // green
  CSV:    '#6366f1',  // indigo
};

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

export function txnMonthKey(dateStr) {
  if (!dateStr) return null;
  // ISO format (YYYY-MM-DD from Teller): append T00:00:00 so it's treated as local time, not UTC.
  // US format (MM/DD/YYYY from Discover/Barclays): pass directly — V8 parses it as local time already.
  const d = /^\d{4}-\d{2}-\d{2}/.test(dateStr)
    ? new Date(dateStr.slice(0, 10) + 'T00:00:00')
    : new Date(dateStr);
  if (isNaN(d)) return null;
  const key   = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  const label = d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  return { key, label };
}
