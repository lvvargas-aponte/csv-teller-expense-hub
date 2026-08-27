import { renderHook, act, waitFor } from '@testing-library/react';
import { usePayoffPlanner } from '../usePayoffPlanner';
import { getAllAccountDetails, upsertAccountDetails } from '../../../../api/accountDetails';

jest.mock('../../../../api/accountDetails');

const creditAccounts = [
  {
    id: 'c1', institution: 'Chase', name: 'Sapphire', ledger: 1200,
  },
];

beforeEach(() => jest.clearAllMocks());

// FIX 2 — PUT /api/accounts/{id}/details is create-or-replace on the
// backend, so sending `{ apr }` alone silently nulls out every other field
// on file for that account (credit_limit, minimum_payment, statement_day,
// due_day, opened_on, notes). Editing an APR must send the full record.
test('editing an APR preserves other fields already on file for the account', async () => {
  getAllAccountDetails.mockResolvedValue({
    data: {
      c1: {
        apr: 19.99,
        credit_limit: 5000,
        minimum_payment: 35,
        statement_day: 12,
        due_day: 28,
        opened_on: '2020-01-15',
        notes: 'Keep under 30% utilization',
      },
    },
  });
  upsertAccountDetails.mockResolvedValue({ data: {} });

  const { result } = renderHook(() => usePayoffPlanner(creditAccounts));

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  const rowId = result.current.rows[0]._id;

  await act(async () => { await result.current.persistApr(rowId, '24.99'); });

  expect(upsertAccountDetails).toHaveBeenCalledWith('c1', expect.objectContaining({
    apr: 24.99,
    credit_limit: 5000,
    due_day: 28,
  }));
});
