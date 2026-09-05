import { renderHook, act, waitFor } from '@testing-library/react';
import { usePayoffPlanner } from '../usePayoffPlanner';
import { getAllAccountDetails } from '../../../../api/accountDetails';

jest.mock('../../../../api/accountDetails');

const CHASE = { id: 'c1', institution: 'Chase', name: 'Sapphire', ledger: 1200 };
const AMEX = { id: 'c2', institution: 'Amex', name: 'Gold', ledger: 800 };

const DETAILS = { c1: { apr: 19.99, minimum_payment: 35, credit_limit: 5000 } };

beforeEach(() => jest.clearAllMocks());

const setup = (accounts = [CHASE], details = DETAILS, onUpdateDetail = jest.fn()) => {
  const { result, rerender } = renderHook(
    ({ accounts: a, details: d, onUpdateDetail: u }) => usePayoffPlanner(a, d, u),
    { initialProps: { accounts, details, onUpdateDetail } },
  );
  return { result, rerender, onUpdateDetail };
};

test('seeds each row from the account and its stored details', async () => {
  const { result } = setup();

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  expect(result.current.rows[0]).toMatchObject({
    accountId: 'c1',
    name: 'Chase Sapphire',
    balance: '1200',
    apr: '19.99',
    min_payment: '35',
  });
});

// The details already live on DebtPage, which loads them once and keeps them
// optimistically merged. A second fetch here was a second copy that went stale.
test('does not fetch details of its own', async () => {
  const { result } = setup();

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  expect(getAllAccountDetails).not.toHaveBeenCalled();
});

// The regression this rewrite exists for: the planner used to seed once behind
// a `prefilled` flag, so a minimum entered in the credit list above never
// arrived — the row stayed blank until the page was reloaded.
test('a minimum payment entered after first render reaches the row', async () => {
  const { result, rerender } = setup([CHASE], { c1: { apr: 19.99 } });

  await waitFor(() => expect(result.current.rows[0].min_payment).toBe(''));

  rerender({
    accounts: [CHASE],
    details: { c1: { apr: 19.99, minimum_payment: 175 } },
    onUpdateDetail: jest.fn(),
  });

  await waitFor(() => expect(result.current.rows[0].min_payment).toBe('175'));
});

test('an account that appears gets a row, and one that goes away loses it', async () => {
  const { result, rerender } = setup([CHASE]);

  await waitFor(() => expect(result.current.rows).toHaveLength(1));

  rerender({ accounts: [CHASE, AMEX], details: DETAILS, onUpdateDetail: jest.fn() });
  await waitFor(() => expect(result.current.rows).toHaveLength(2));

  // A card closed via closed_on drops out of DebtPage's payoffAccounts.
  rerender({ accounts: [AMEX], details: DETAILS, onUpdateDetail: jest.fn() });
  await waitFor(() => expect(result.current.rows.map((r) => r.accountId)).toEqual(['c2']));
});

test('a row added by hand is not swept away when the details change', async () => {
  const { result, rerender } = setup();

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  act(() => { result.current.addRow(); });
  expect(result.current.rows).toHaveLength(2);

  rerender({
    accounts: [CHASE],
    details: { c1: { apr: 22.5, minimum_payment: 35 } },
    onUpdateDetail: jest.fn(),
  });

  await waitFor(() => expect(result.current.rows.find((r) => r.accountId)?.apr).toBe('22.5'));
  expect(result.current.rows.filter((r) => !r.accountId)).toHaveLength(1);
});

// Balance is the one field that does not round-trip: it comes from the bank,
// so typing one here is a scenario, not a correction.
test('a balance typed into the planner survives an unrelated details edit', async () => {
  const { result, rerender } = setup();

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  const rowId = result.current.rows[0]._id;
  act(() => { result.current.setRow(rowId, 'balance', '999'); });

  rerender({
    accounts: [CHASE],
    details: { c1: { apr: 24.99, minimum_payment: 35 } },
    onUpdateDetail: jest.fn(),
  });

  await waitFor(() => expect(result.current.rows[0].apr).toBe('24.99'));
  expect(result.current.rows[0].balance).toBe('999');
});

test('a balance the bank itself moved replaces the local one', async () => {
  const { result, rerender } = setup();

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  act(() => { result.current.setRow(result.current.rows[0]._id, 'balance', '999'); });

  rerender({
    accounts: [{ ...CHASE, ledger: 1350 }],
    details: DETAILS,
    onUpdateDetail: jest.fn(),
  });

  await waitFor(() => expect(result.current.rows[0].balance).toBe('1350'));
});

// The planner is a read-only view: an account's balance, APR and minimum are
// edited in the Credit cards drawer above, which is the one place they live.
// The hook therefore exposes no writer at all.
test('exposes no way to write back to an account', async () => {
  const { result } = setup();

  await waitFor(() => expect(result.current.rows).toHaveLength(1));
  expect(result.current.persistDetail).toBeUndefined();
});
