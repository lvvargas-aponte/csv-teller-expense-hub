import { buildCreditRow } from '../accountMath';

// balances_service copies the amount owed into `available` for every credit
// account — SimpleFIN has no available-credit figure to give it. Trusting that
// field is what made a card with a $19,200 limit and $438 owed report
// "$438 available" on both /accounts and /debt.
const card = (over = {}) => ({
  id: 'c1',
  name: 'Amazon Prime Rewards',
  institution: 'Chase',
  type: 'credit',
  ledger: 438.68,
  available: 438.68,
  manual: false,
  ...over,
});

test('derives available credit from the stored limit', () => {
  const row = buildCreditRow(card(), { credit_limit: 19200 });

  expect(row.available).toBeCloseTo(18761.32, 2);
});

test('reports no available credit when no limit is stored', () => {
  const row = buildCreditRow(card(), {});

  expect(row.available).toBeNull();
});

// Owed above the limit is a real state (over-limit fees, interest posted after
// the statement). There is no negative amount of available credit.
test('an over-limit card has no available credit, not a negative amount', () => {
  const row = buildCreditRow(card({ ledger: 5000, available: 5000 }), { credit_limit: 3500 });

  expect(row.available).toBe(0);
});

// A manual card is the one place the field can hold something real — the Add
// form asks for it — and the only tell is that it differs from what's owed.
test('keeps the available credit entered on a manual card', () => {
  const row = buildCreditRow(
    card({ manual: true, ledger: 1200, available: 3800 }),
    {},
  );

  expect(row.available).toBe(3800);
});

test('ignores a manual available that is just a copy of the balance', () => {
  const row = buildCreditRow(card({ manual: true, ledger: 1200, available: 1200 }), {});

  expect(row.available).toBeNull();
});

// A typed figure goes stale as the balance moves; limit − owed does not.
test('a stored limit wins over a manually entered figure', () => {
  const row = buildCreditRow(
    card({ manual: true, ledger: 1200, available: 3800 }),
    { credit_limit: 10000 },
  );

  expect(row.available).toBe(8800);
});

test('a synced card never has its reported available treated as real', () => {
  const row = buildCreditRow(card({ ledger: 1200, available: 3800 }), {});

  expect(row.available).toBeNull();
});