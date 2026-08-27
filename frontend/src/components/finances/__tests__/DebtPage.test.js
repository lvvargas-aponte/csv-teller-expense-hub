import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import DebtPage from '../DebtPage';
import { getCreditHealth, getCreditFactors } from '../../../api/dashboard';
import { getAllAccountDetails } from '../../../api/accountDetails';
import { updateAccountBalance, deleteManualAccount } from '../../../api/balances';

jest.mock('../../../api/dashboard');
jest.mock('../../../api/accountDetails');
jest.mock('../../../api/balances');

const summary = {
  accounts: [
    { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820, due_day: 14 },
    { id: 'c2', name: 'Amex Gold', institution: 'Amex', type: 'credit', ledger: 1240, due_day: 2 },
    { id: 'd1', name: 'Ally Savings', institution: 'Ally', type: 'depository', available: 18400 },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  getCreditHealth.mockResolvedValue({
    data: {
      overall_utilization_pct: 42, overall_status: 'warn', total_balance: 6060, total_limit: 14400,
      accounts: [{
        account_id: 'c1', institution: 'Chase', name: 'Chase Sapphire',
        balance: 4820, credit_limit: 10000, utilization_pct: 48, status: 'warn',
      }],
    },
  });
  getCreditFactors.mockResolvedValue({
    data: {
      utilization: {}, payment_timeliness: {}, history: {}, new_credit: {}, mix: {},
      coverage_note: 'Measured on connected accounts.',
    },
  });
  getAllAccountDetails.mockResolvedValue({ data: {} });
  updateAccountBalance.mockResolvedValue({ data: {} });
  deleteManualAccount.mockResolvedValue({ data: {} });
});

const renderPage = (props = {}) => render(
  <MemoryRouter><DebtPage summary={summary} onRefresh={jest.fn()} {...props} /></MemoryRouter>,
);

test('names itself Debt', async () => {
  renderPage();
  expect(await screen.findByRole('heading', { level: 1, name: 'Debt' })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

test('totals only what is owed, ignoring cash', async () => {
  renderPage();
  const summarySection = screen.getByRole('region', { name: 'Debt summary' });
  expect(await within(summarySection).findByText(/6,060/)).toBeInTheDocument();
  expect(screen.queryByText(/18,400/)).toBeNull();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

test('reports utilization from the API rather than recomputing it', async () => {
  renderPage();
  const summarySection = screen.getByRole('region', { name: 'Debt summary' });
  expect(await within(summarySection).findByText(/42%/)).toBeInTheDocument();
  expect(getCreditHealth).toHaveBeenCalled();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

test('utilization is not conveyed by colour alone', async () => {
  renderPage();
  // A colour-coded status must carry text too — see the repo's a11y commit.
  // Scoped to the summary section: the payoff planner below also has text
  // matching this pattern ("Avalanche — High APR first").
  const summarySection = screen.getByRole('region', { name: 'Debt summary' });
  expect(await within(summarySection).findByText(/42%/)).toBeInTheDocument();
  expect(within(summarySection).getByText(/warn|watch|high/i)).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

test('survives a credit-health outage without blanking the page', async () => {
  getCreditHealth.mockRejectedValue(new Error('down'));
  renderPage();
  expect(await screen.findByRole('heading', { level: 1, name: 'Debt' })).toBeInTheDocument();
  const summarySection = screen.getByRole('region', { name: 'Debt summary' });
  expect(within(summarySection).getByText(/6,060/)).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

test('the next payment is the nearest upcoming date, not the smallest day number', async () => {
  jest.useFakeTimers().setSystemTime(new Date('2026-08-20T12:00:00Z'));
  // due_day 25 is five days out; due_day 2 already passed and wraps to next month.
  renderPage({ summary: { accounts: [
    { id: 'c1', name: 'Near Card', institution: 'A', type: 'credit', ledger: 100, due_day: 25 },
    { id: 'c2', name: 'Far Card', institution: 'B', type: 'credit', ledger: 100, due_day: 2 },
  ] } });

  expect(await screen.findByText(/Near Card/)).toBeInTheDocument();
  expect(screen.queryByText(/Far Card/)).toBeNull();
  jest.useRealTimers();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

// --- The moved credit list ---------------------------------------------
// Everything below used to be exercised through AccountsTab. The rows,
// their drawer, the manual-balance editor and the add flow moved to /debt
// in Phase 4 Task 2, and this coverage moved with them.

test('lists credit accounts with their editable detail', async () => {
  const user = userEvent.setup();
  renderPage();

  const row = await screen.findByRole('group', { name: /chase sapphire/i });
  await user.click(within(row).getByRole('button', { name: /chase sapphire/i }));

  for (const label of ['Credit limit', 'APR', 'Min payment', 'Statement day', 'Due day', 'Opened on']) {
    expect(within(row).getByLabelText(label)).toBeInTheDocument();
  }
});

test('offers adding a credit card or loan', async () => {
  renderPage();
  expect(await screen.findByRole('button', { name: /add credit card or loan/i })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

const LONG_NAME = 'Customized Cash Rewards Visa Signature 7473';

test('a long account name renders in full, with no truncation', async () => {
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 2011.65 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  expect(within(row).getByText(LONG_NAME)).toBeInTheDocument();
});

test('empty metadata is omitted from the meta line rather than shown as dashes', async () => {
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 2011.65 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  expect(row).toHaveTextContent('Bank of America');
  expect(row).not.toHaveTextContent('—');
  expect(row).not.toHaveTextContent(/APR|used|due day|min \$/);
});

test('populated metadata appears in the meta line', async () => {
  getAllAccountDetails.mockResolvedValue({
    data: { c1: { credit_limit: 3500, apr: 21.99, minimum_payment: 37 } },
  });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 2011.65 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  await waitFor(() => expect(row).toHaveTextContent('43% used'));
  expect(row).toHaveTextContent('21.99% APR');
  expect(row).toHaveTextContent('min $37.00');
});

test('editing the credit limit on a manual card recomputes its available credit', async () => {
  const user = userEvent.setup();
  getAllAccountDetails.mockResolvedValue({ data: { m1: { credit_limit: 4000 } } });
  renderPage({ summary: { accounts: [
    { id: 'm1', name: 'Discover', institution: 'Discover', type: 'credit', manual: true, ledger: 1000, available: 0 },
  ] } });

  const row = await screen.findByRole('group', { name: /discover/i });
  await waitFor(() => expect(within(row).getByText('$3,000.00 available')).toBeInTheDocument());

  await user.click(within(row).getByRole('button', { name: /discover/i }));
  const limitInput = screen.getByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '5000');
  await user.tab();

  await waitFor(() => {
    expect(within(row).getByText('$4,000.00 available')).toBeInTheDocument();
  });
});

test("a synced card keeps the bank's available credit when the limit is edited", async () => {
  const user = userEvent.setup();
  getAllAccountDetails.mockResolvedValue({ data: { c1: { credit_limit: 3500 } } });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 2011.65 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  await user.click(within(row).getByRole('button', { name: new RegExp(LONG_NAME) }));
  const limitInput = await screen.findByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '9000');
  await user.tab();

  // Utilization follows the new limit, but availability stays the bank's number.
  await waitFor(() => expect(within(row).getByText('$2,011.65 available')).toBeInTheDocument());
  expect(row).toHaveTextContent('17% used');
});

test('the open date is editable and survives an edit to another field', async () => {
  const user = userEvent.setup();
  getAllAccountDetails.mockResolvedValue({
    data: { c1: { credit_limit: 3500, opened_on: '2016-04-02' } },
  });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 2011.65 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  await user.click(within(row).getByRole('button', { name: new RegExp(LONG_NAME) }));

  const opened = await screen.findByPlaceholderText('YYYY-MM-DD');
  expect(opened).toHaveValue('2016-04-02');

  const limitInput = screen.getByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '5000');
  await user.tab();

  await waitFor(() => expect(opened).toHaveValue('2016-04-02'));
});

test('a card you just paid off stays listed and is marked paid off', async () => {
  renderPage({ summary: { accounts: [
    { id: 'pc1', name: 'Cleared Visa', institution: 'Visa', type: 'credit', ledger: 0 },
  ] } });

  const row = await screen.findByRole('group', { name: /cleared visa/i });
  expect(within(row).getByText('Paid off')).toBeInTheDocument();
});

test('a card carrying a balance is not marked paid off', async () => {
  renderPage({ summary: { accounts: [
    { id: 'bc1', name: 'Carrying Balance Card', institution: 'Visa', type: 'credit', ledger: 500 },
  ] } });

  const row = await screen.findByRole('group', { name: /carrying balance card/i });
  expect(within(row).queryByText('Paid off')).toBeNull();
});

test('a row shows a needs-reconnect state for a broken connection', async () => {
  renderPage({ summary: { accounts: [
    { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820 },
  ],
  connections: [{ institution: 'Chase', status: 'disconnected', last_error: 'Auth failed (403)' }] } });

  const row = await screen.findByRole('group', { name: /chase sapphire/i });
  expect(row).toHaveTextContent('needs reconnect');
});

test("a manual credit account's balance editor pre-fills the starting balance, not the live computed one", async () => {
  const user = userEvent.setup();
  renderPage({ summary: { accounts: [
    {
      id: 'm1', name: 'Manual Card', institution: '', type: 'credit', manual: true,
      ledger: 950, available: 500, starting_balance: 1000, linked_txn_count: 3,
    },
  ] } });

  const row = await screen.findByRole('group', { name: /manual card/i });
  // The row itself still shows the live, computed number.
  expect(within(row).getByText('$950.00')).toBeInTheDocument();

  await user.click(within(row).getByRole('button', { name: /edit balance/i }));
  expect(within(row).getByLabelText(/balance owed/i)).toHaveValue(1000);
  expect(within(row).getByText(/from 3 linked txns/i)).toBeInTheDocument();

  await user.click(within(row).getByRole('button', { name: /save/i }));

  expect(updateAccountBalance).toHaveBeenCalledWith(
    'm1',
    expect.objectContaining({ ledger: 1000 }),
  );
});

test('carries the payoff planner and the credit factors', async () => {
  renderPage();
  expect(await screen.findByRole('heading', { name: /payoff/i })).toBeInTheDocument();
  // /credit/i alone also matches the "Credit cards & loans" section heading
  // already on this page — scope to the factors panel's own title.
  expect(screen.getByRole('heading', { name: /credit factors/i })).toBeInTheDocument();
});

test('shows the utilization card', async () => {
  renderPage();
  // "$6,060.00 of $14,400.00" is split across sibling <Num> spans, so match
  // on the containing element's full textContent rather than a single node.
  const matches = await screen.findAllByText(
    (_, el) => /of \$?14,400/i.test(el.textContent || ''),
  );
  expect(matches.length).toBeGreaterThan(0);
});

test('deleting a manual credit account asks first', async () => {
  const user = userEvent.setup();
  jest.spyOn(window, 'confirm').mockReturnValue(false);
  renderPage({ summary: { accounts: [
    { id: 'm1', name: 'Manual Card', institution: '', type: 'credit', manual: true, ledger: 300, available: 200 },
  ] } });

  const row = await screen.findByRole('group', { name: /manual card/i });
  await user.click(within(row).getByRole('button', { name: /remove/i }));

  expect(window.confirm).toHaveBeenCalled();
  expect(deleteManualAccount).not.toHaveBeenCalled();
  window.confirm.mockRestore();
});
