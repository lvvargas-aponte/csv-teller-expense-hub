// Days from today until the next occurrence of `dueDay` (a 1-31 day-of-month).
// If today is on or before the day this month, target is this month; otherwise
// next month. Returns null when dueDay is missing.
export function daysUntilNextDue(dueDay) {
  if (!dueDay) return null;
  const today = new Date();
  const y = today.getFullYear();
  const m = today.getMonth();
  const thisMonth = new Date(y, m, dueDay);
  const nextMonth = new Date(y, m + 1, dueDay);
  const target = today.getDate() <= dueDay ? thisMonth : nextMonth;
  const diffMs = target.getTime() - new Date(y, m, today.getDate()).getTime();
  return Math.max(0, Math.round(diffMs / (1000 * 60 * 60 * 24)));
}

export function dueUrgencyClass(days) {
  if ((days === null || days === undefined)) return '';
  if (days <= 3) return 'due-urgent';
  if (days <= 7) return 'due-soon';
  return '';
}
