import { renderHook, act, waitFor } from '@testing-library/react';
import useSyncAll from '../useSyncAll';
import { syncSimplefin } from '../../api/simplefin';
import { syncSnapTrade } from '../../api/snaptrade';

jest.mock('../../api/simplefin');
jest.mock('../../api/snaptrade');

beforeEach(() => jest.clearAllMocks());

test('runs both providers and then refreshes', async () => {
  syncSimplefin.mockResolvedValue({});
  syncSnapTrade.mockResolvedValue({});
  const onRefresh = jest.fn().mockResolvedValue();

  const { result } = renderHook(() => useSyncAll({ onRefresh, hasBrokerages: true }));
  await act(async () => { await result.current.syncAll(); });

  expect(syncSimplefin).toHaveBeenCalled();
  expect(syncSnapTrade).toHaveBeenCalled();
  expect(onRefresh).toHaveBeenCalled();
  expect(result.current.syncError).toBeNull();
});

test('a brokerage failure does not hide a successful bank sync', async () => {
  syncSimplefin.mockResolvedValue({});
  syncSnapTrade.mockRejectedValue(new Error('snaptrade down'));

  const { result } = renderHook(() => useSyncAll({ onRefresh: jest.fn(), hasBrokerages: true }));
  await act(async () => { await result.current.syncAll(); });

  expect(result.current.syncError).toMatch(/brokerages/i);
  expect(result.current.syncError).not.toMatch(/failed/i);
});

test('reports total failure when both providers fail', async () => {
  syncSimplefin.mockRejectedValue(new Error('down'));
  syncSnapTrade.mockRejectedValue(new Error('down'));

  const { result } = renderHook(() => useSyncAll({ onRefresh: jest.fn(), hasBrokerages: true }));
  await act(async () => { await result.current.syncAll(); });

  expect(result.current.syncError).toMatch(/sync failed/i);
});

test('refreshes even when a provider failed, so cached data is not left stale', async () => {
  syncSimplefin.mockRejectedValue(new Error('down'));
  syncSnapTrade.mockResolvedValue({});
  const onRefresh = jest.fn();

  const { result } = renderHook(() => useSyncAll({ onRefresh, hasBrokerages: true }));
  await act(async () => { await result.current.syncAll(); });

  expect(onRefresh).toHaveBeenCalled();
});

test('exposes syncing while in flight and clears it after', async () => {
  let release;
  syncSimplefin.mockReturnValue(new Promise((r) => { release = r; }));
  syncSnapTrade.mockResolvedValue({});

  const { result } = renderHook(() => useSyncAll({ onRefresh: jest.fn(), hasBrokerages: true }));
  act(() => { result.current.syncAll(); });
  await waitFor(() => expect(result.current.syncing).toBe(true));

  await act(async () => { release({}); });
  await waitFor(() => expect(result.current.syncing).toBe(false));
});

// FIX 2(a) — a SimpleFIN-only user is the common case, and SnapTrade must
// not even be called, since POST /api/snaptrade/sync answers 503/409 for a
// user who has never set it up, and calling-then-ignoring still cost a
// round trip and a console error in the old implementation.
test('a SimpleFIN-only sync never calls SnapTrade and reports no error', async () => {
  syncSimplefin.mockResolvedValue({});
  const onRefresh = jest.fn().mockResolvedValue();

  const { result } = renderHook(() => useSyncAll({ onRefresh, hasBrokerages: false }));
  await act(async () => { await result.current.syncAll(); });

  expect(syncSimplefin).toHaveBeenCalled();
  expect(syncSnapTrade).not.toHaveBeenCalled();
  expect(result.current.syncError).toBeNull();
});

// FIX 2(a) — even when brokerages are worth trying, an unconfigured (503)
// or unconnected (409) provider is not a sync failure.
test.each([503, 409])('a %i from SnapTrade is treated as not applicable, not a failure', async (status) => {
  syncSimplefin.mockResolvedValue({});
  syncSnapTrade.mockRejectedValue({ response: { status } });

  const { result } = renderHook(() => useSyncAll({ onRefresh: jest.fn(), hasBrokerages: true }));
  await act(async () => { await result.current.syncAll(); });

  expect(result.current.syncError).toBeNull();
});
