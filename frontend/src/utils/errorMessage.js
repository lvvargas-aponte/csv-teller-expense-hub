// Extract a safe, user-facing message from an axios error.
// Returns the backend `detail` only if it looks like a curated short string;
// otherwise falls back to the caller's generic message. This keeps stack
// traces and internal exception text out of the UI.

const TRACEBACK_HINT = /\b(traceback|at\s+\w+\s*\(|line\s+\d+,\s+in\s+|File\s+"[^"]+")/i;
const MAX_DETAIL_LEN = 200;

export function userMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail.length > 0 && detail.length <= MAX_DETAIL_LEN && !TRACEBACK_HINT.test(detail)) {
    return detail;
  }
  return fallback;
}
