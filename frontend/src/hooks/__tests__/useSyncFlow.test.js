import { renderHook, act } from '@testing-library/react';
import axios from 'axios';
import { useSyncFlow } from '../useSyncFlow';

jest.mock('axios');

beforeEach(() => jest.clearAllMocks());

// FIX 6 — SyncContext no-ops a page's registered `setError` once that page
// unmounts (to avoid writing into a dead callback), but a bank sync or Sheet
// send that fails after navigating away used to report nothing at all:
// setError was the only place a failure went, and it had just become a
// no-op. setSyncToast lives at the shell level and survives, so failures
// must also route there.

test('a failing bank sync still surfaces via syncToast when setError is a no-op (page unmounted)', async () => {
  axios.post.mockRejectedValue({ response: { data: { detail: 'boom' } } });
  const reload = jest.fn();
  const setError = jest.fn(); // stands in for SyncContext's post-unmount no-op

  const { result } = renderHook(() => useSyncFlow({
    reload, setError, filterMonth: 'all', sharedCount: 0,
  }));

  await act(async () => {
    await result.current.syncBanks('2026-01-01', '2026-01-31', null);
  });

  expect(result.current.syncToast).toEqual(
    expect.objectContaining({ error: expect.stringContaining('boom') }),
  );
});

test('a failing Sheet send still surfaces via syncToast when setError is a no-op (page unmounted)', async () => {
  jest.spyOn(window, 'confirm').mockReturnValue(true);
  axios.post.mockRejectedValue({ response: { data: { detail: 'sheet down' } } });
  const reload = jest.fn();
  const setError = jest.fn();

  const { result } = renderHook(() => useSyncFlow({
    reload, setError, filterMonth: 'all', sharedCount: 2,
  }));

  await act(async () => {
    await result.current.sendToSheet();
  });

  expect(result.current.syncToast).toEqual(
    expect.objectContaining({ error: expect.stringContaining('sheet down') }),
  );

  window.confirm.mockRestore();
});

test('a successful bank sync sets a normal (non-error) toast', async () => {
  axios.post.mockResolvedValue({ data: { total_new: 3, from_date: '2026-01-01', to_date: '2026-01-31' } });
  const reload = jest.fn();
  const setError = jest.fn();

  const { result } = renderHook(() => useSyncFlow({
    reload, setError, filterMonth: 'all', sharedCount: 0,
  }));

  await act(async () => {
    await result.current.syncBanks('2026-01-01', '2026-01-31', null);
  });

  expect(result.current.syncToast).toEqual(
    expect.objectContaining({ total_new: 3 }),
  );
  expect(result.current.syncToast.error).toBeUndefined();
});
