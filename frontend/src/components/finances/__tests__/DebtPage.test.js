import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import DebtPage from '../DebtPage';
import { getCreditHealth, getBorrowingPower } from '../../../api/dashboard';
import { getAllAccountDetails, upsertAccountDetails } from '../../../api/accountDetails';
import { updateAccountBalance, deleteManualAccount } from '../../../api/balances';

jest.mock('../../../api/dashboard');
jest.mock('../../../api/accountDetails');
jest.mock('../../../api/balances');

const summary = {
  accounts: [
    { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820 },
    { id: 'c2', name: 'Amex Gold', institution: 'Amex', type: 'credit', ledger: 1240 },
    { id: 'd1', name: 'Ally Savings', institution: 'Ally', type: 'depository', available: 18400 },
  ],
};

// `due_day` (and every other user-supplied detail) is served only from the
// account_details side-car, never from balances-summary accounts — see
// AccountBalance in backend/models.py. These fixtures route it through
// getAllAccountDetails so tests exercise the shape the API actually returns.
const DUE_DAY_DETAILS = { c1: { due_day: 14 }, c2: { due_day: 2 } };

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
  getBorrowingPower.mockResolvedValue({
    data: {
      dti: { pct: null, debts_missing_payment: [] },
      interest_history: { months: [], total_paid: 0, latest: null, average: null, trend: null, highest: null },
      carry_cost: { monthly_interest: 0, accounts_missing_apr: 0 },
    },
  });
  getAllAccountDetails.mockResolvedValue({ data: {} });
  upsertAccountDetails.mockResolvedValue({ data: {} });
  updateAccountBalance.mockResolvedValue({ data: {} });
  deleteManualAccount.mockResolvedValue({ data: {} });
});

// The planner's row for Chase Sapphire. Account rows render as text rather
// than inputs, so this matches on the name cell.
const plannerRow = () => screen.getAllByRole('row')
  .find((r) => within(r).queryByText('Chase Chase Sapphire'));

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

test('no credit limits set does not print a bare "%"', async () => {
  getCreditHealth.mockResolvedValue({
    data: {
      overall_utilization_pct: null, overall_status: 'unknown', total_balance: 6060, total_limit: 0,
      accounts: [],
    },
  });
  renderPage();
  await screen.findByRole('heading', { level: 1, name: 'Debt' });
  const summarySection = screen.getByRole('region', { name: 'Debt summary' });
  expect(within(summarySection).queryByText('Utilization')).toBeNull();
  expect(within(summarySection).queryByText(/^%$/)).toBeNull();
  expect(within(summarySection).queryByText(/null%/)).toBeNull();
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
  getAllAccountDetails.mockResolvedValue({ data: { c1: { due_day: 25 }, c2: { due_day: 2 } } });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: 'Near Card', institution: 'A', type: 'credit', ledger: 100 },
    { id: 'c2', name: 'Far Card', institution: 'B', type: 'credit', ledger: 100 },
  ] } });

  const summarySection = await screen.findByRole('region', { name: 'Debt summary' });
  expect(await within(summarySection).findByText(/Near Card/)).toBeInTheDocument();
  expect(within(summarySection).queryByText(/Far Card/)).toBeNull();
  // The line must actually render a day, not silently stay hidden.
  expect(within(summarySection).getByText('Day 25')).toBeInTheDocument();
  jest.useRealTimers();
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
});

test('reports the next payment due date, sourced from account details not the summary payload', async () => {
  jest.useFakeTimers().setSystemTime(new Date('2026-08-01T12:00:00Z'));
  getAllAccountDetails.mockResolvedValue({ data: DUE_DAY_DETAILS });
  renderPage();

  const summarySection = await screen.findByRole('region', { name: 'Debt summary' });
  expect(await within(summarySection).findByText('Next payment due')).toBeInTheDocument();
  expect(within(summarySection).getByText('Day 2')).toBeInTheDocument();
  expect(within(summarySection).getByText(/Amex Gold/)).toBeInTheDocument();
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

// This used to assert that a synced card kept "the bank's" available credit.
// There is no such number: balances_service copies the owed amount into
// `available` for every credit account, so honouring it printed the balance
// twice — once as owed and once as available. Editing the limit is what moves
// available credit, because limit − owed is the only figure that exists.
test('editing the limit moves a synced card"s available credit', async () => {
  const user = userEvent.setup();
  getAllAccountDetails.mockResolvedValue({ data: { c1: { credit_limit: 3500 } } });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 1488.35 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  expect(within(row).getByText('$2,011.65 available')).toBeInTheDocument();

  await user.click(within(row).getByRole('button', { name: new RegExp(LONG_NAME) }));
  const limitInput = await screen.findByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '9000');
  await user.tab();

  await waitFor(() => expect(within(row).getByText('$7,511.65 available')).toBeInTheDocument());
  expect(row).toHaveTextContent('17% used');
});

test('a card with no stored limit shows what is owed and nothing else', async () => {
  getAllAccountDetails.mockResolvedValue({ data: {} });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: LONG_NAME, institution: 'Bank of America', type: 'credit', ledger: 1488.35, available: 1488.35 },
  ] } });

  const row = await screen.findByRole('group', { name: new RegExp(LONG_NAME) });
  expect(within(row).getByText('$1,488.35')).toBeInTheDocument();
  expect(within(row).queryByText(/available/i)).toBeNull();
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

  // Two fields share this placeholder now (Opened on, Closed on), so go by label.
  const opened = await within(row).findByLabelText('Opened on');
  expect(opened).toHaveValue('2016-04-02');

  const limitInput = screen.getByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '5000');
  await user.tab();

  await waitFor(() => expect(opened).toHaveValue('2016-04-02'));

  // Length of history is the one factor a bank feed cannot infer, so an edit
  // to any other field must not quietly drop it from the PUT. Assert on the
  // wire, not just the (optimistically-merged) displayed value — see the
  // note in AccountsTab.test.js about this test's history.
  await waitFor(() => expect(upsertAccountDetails).toHaveBeenCalled());
  const [, payload] = upsertAccountDetails.mock.calls[upsertAccountDetails.mock.calls.length - 1];
  expect(payload.opened_on).toBe('2016-04-02');
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

test('carries the payoff planner and the borrowing-power panel', async () => {
  renderPage();
  expect(await screen.findByRole('heading', { name: /payoff/i })).toBeInTheDocument();
  // /credit/i alone also matches the "Credit cards & loans" section heading
  // already on this page — scope to the panel's own title.
  expect(screen.getByRole('heading', { name: /borrowing power/i })).toBeInTheDocument();
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

// --- "set limit" on the utilization card --------------------------------
// The card sits below the credit list and used to render `set limit →` as
// plain text: it read as a link and did nothing. It now opens the drawer of
// the row that holds the field, which is the only place a limit is entered.

const NO_LIMIT_HEALTH = {
  data: {
    overall_utilization_pct: 48, overall_status: 'warn',
    total_balance: 6060, total_limit: 10000,
    accounts: [
      {
        account_id: 'c1', institution: 'Chase', name: 'Chase Sapphire',
        balance: 4820, credit_limit: 10000, utilization_pct: 48, status: 'warn',
      },
      {
        account_id: 'c2', institution: 'Amex', name: 'Amex Gold',
        balance: 1240, credit_limit: null, utilization_pct: null, status: 'unknown',
      },
    ],
  },
};

test('"set limit" opens the drawer of the card it names', async () => {
  const user = userEvent.setup();
  getCreditHealth.mockResolvedValue(NO_LIMIT_HEALTH);
  renderPage();

  const row = await screen.findByRole('group', { name: /amex gold/i });
  expect(within(row).queryByLabelText('Credit limit')).toBeNull();

  await user.click(await screen.findByRole('button', { name: /set limit for amex gold/i }));

  expect(within(row).getByLabelText('Credit limit')).toHaveFocus();
});

test('opening one drawer closes another', async () => {
  const user = userEvent.setup();
  renderPage();

  const chase = await screen.findByRole('group', { name: /chase sapphire/i });
  const amex = screen.getByRole('group', { name: /amex gold/i });

  await user.click(within(chase).getByRole('button', { name: /chase sapphire/i }));
  expect(within(chase).getByLabelText('APR')).toBeInTheDocument();

  await user.click(within(amex).getByRole('button', { name: /amex gold/i }));
  expect(within(chase).queryByLabelText('APR')).toBeNull();
  expect(within(amex).getByLabelText('APR')).toBeInTheDocument();
});

test('says the add button is for hand-maintained cards, and where to connect a real one', async () => {
  renderPage();

  const note = await screen.findByText(/maintain yourself/i);
  expect(note).toHaveTextContent(/nothing updates it/i);
  expect(within(note).getByRole('link', { name: /connect a bank or card/i }))
    .toHaveAttribute('href', '/accounts');
});

// --- Closed accounts ----------------------------------------------------
// SimpleFIN has no open/closed concept, so a closed card keeps arriving on
// every fetch. Declaring it closed is the only way to get it out of the way,
// and it must not take its history with it.

const CLOSED_SUMMARY = { accounts: [
  { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820 },
  { id: 'c2', name: 'Amex Gold', institution: 'Amex', type: 'credit', ledger: 1240, closed_on: '2026-05-01' },
] };

test('a closed card leaves the live list and the total owed', async () => {
  const user = userEvent.setup();
  renderPage({ summary: CLOSED_SUMMARY });

  // The Closed group starts collapsed, so the card is out of the DOM entirely
  // until asked for — and back once it is.
  expect(await screen.findByRole('group', { name: /chase sapphire/i })).toBeInTheDocument();
  expect(screen.queryByRole('group', { name: /amex gold/i })).toBeNull();

  // 4,820 alone — not the 6,060 both cards would total.
  const summarySection = screen.getByRole('region', { name: 'Debt summary' });
  expect(within(summarySection).getByText(/4,820/)).toBeInTheDocument();
  expect(within(summarySection).queryByText(/6,060/)).toBeNull();

  await user.click(screen.getByRole('button', { name: /^closed/i }));
  expect(screen.getByRole('group', { name: /amex gold/i })).toBeInTheDocument();
});

test('the closed section is collapsed until asked for', async () => {
  const user = userEvent.setup();
  renderPage({ summary: CLOSED_SUMMARY });

  const toggle = await screen.findByRole('button', { name: /^closed/i });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');

  await user.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
});

test('no closed cards means no closed section', async () => {
  renderPage();

  await screen.findByRole('group', { name: /chase sapphire/i });
  expect(screen.queryByRole('button', { name: /^closed/i })).toBeNull();
});

// The closed date is the only way back — a row that lost its drawer would be
// closed forever.
test('a closed card keeps its drawer so the date can be cleared', async () => {
  const user = userEvent.setup();
  renderPage({ summary: CLOSED_SUMMARY });

  await user.click(await screen.findByRole('button', { name: /^closed/i }));
  const row = screen.getByRole('group', { name: /amex gold/i });
  await user.click(within(row).getByRole('button', { name: /amex gold/i }));

  expect(within(row).getByLabelText('Closed on')).toHaveValue('2026-05-01');
});

test('the closed date is written through to account details', async () => {
  const user = userEvent.setup();
  renderPage();

  const row = await screen.findByRole('group', { name: /chase sapphire/i });
  await user.click(within(row).getByRole('button', { name: /chase sapphire/i }));
  // Clear first: InlineField selects its contents on focus via rAF, which
  // races the first keystroke otherwise (the limit tests above do the same).
  const closedOn = within(row).getByLabelText('Closed on');
  await user.clear(closedOn);
  await user.type(closedOn, '2026-09-01');
  await user.tab();

  await waitFor(() => expect(upsertAccountDetails).toHaveBeenCalled());
  const [id, payload] = upsertAccountDetails.mock.calls[upsertAccountDetails.mock.calls.length - 1];
  expect(id).toBe('c1');
  expect(payload.closed_on).toBe('2026-09-01');
});

// --- The credit list and the payoff planner share one record ------------
// The planner used to seed once from its own details fetch, so anything
// entered in the drawer above after first paint never reached it.

test('a minimum payment entered in the drawer reaches the payoff planner', async () => {
  const user = userEvent.setup();
  renderPage({ summary: { accounts: [
    { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820 },
  ] } });

  const row = await screen.findByRole('group', { name: /chase sapphire/i });
  expect(within(plannerRow()).getByText('$4,820.00')).toBeInTheDocument();

  await user.click(within(row).getByRole('button', { name: /chase sapphire/i }));
  const min = within(row).getByLabelText('Min payment');
  await user.clear(min);
  await user.type(min, '175');
  await user.tab();

  await waitFor(() => expect(within(plannerRow()).getByText('$175.00')).toBeInTheDocument());
});

// Nothing about an account is editable in the planner — its values belong to
// the Credit cards list above, and two places to type the same fact is what
// let them disagree.
test('an account row in the planner cannot be edited', async () => {
  getAllAccountDetails.mockResolvedValue({ data: { c1: { apr: 19.99, minimum_payment: 35 } } });
  renderPage({ summary: { accounts: [
    { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', ledger: 4820 },
  ] } });

  await screen.findByRole('group', { name: /chase sapphire/i });
  const planner = within(plannerRow());

  // Values are shown, but as text — no inputs, no APR button, no remove.
  expect(planner.getByText('$4,820.00')).toBeInTheDocument();
  expect(planner.getByText('19.99%')).toBeInTheDocument();
  expect(planner.getByText('$35.00')).toBeInTheDocument();
  expect(planner.queryAllByRole('textbox')).toHaveLength(0);
  expect(planner.queryAllByRole('spinbutton')).toHaveLength(0);
  expect(planner.queryByRole('button', { name: /remove debt/i })).toBeNull();
});

// The planner's own inputs are a different matter — they are what it is for.
test('the strategy and extra payment stay editable', async () => {
  const user = userEvent.setup();
  renderPage();

  await screen.findByRole('group', { name: /chase sapphire/i });
  // The visible label is the accessible name now: a shorter aria-label used to
  // override it, which breaks voice control (WCAG 2.5.3, Label in Name).
  const extra = screen.getByLabelText('Extra monthly payment toward debt');
  await user.clear(extra);
  await user.type(extra, '350');
  expect(extra).toHaveValue(350);

  await user.click(screen.getByRole('button', { name: /snowball/i }));
  expect(screen.getByRole('button', { name: /snowball/i })).toHaveClass('ov-strategy-tab--active');
});

// --- Loans are not cards ------------------------------------------------
// A mortgage is credit, but it has no limit and a fixed schedule. It gets its
// own section and stays out of the payoff planner, whose avalanche/snowball
// ordering only applies to revolving balances.

const WITH_LOAN = { accounts: [
  { id: 'c1', name: 'Chase Sapphire', institution: 'Chase', type: 'credit', subtype: 'credit_card', ledger: 4820 },
  { id: 'l1', name: 'Mortgage 3934', institution: 'Truist', type: 'credit', subtype: 'loan', ledger: 419391.99 },
] };

test('a loan is listed under Loans, not Credit cards', async () => {
  renderPage({ summary: WITH_LOAN });

  const cards = await screen.findByRole('button', { name: /^credit cards/i });
  const loans = screen.getByRole('button', { name: /^loans/i });

  expect(cards).toHaveTextContent('1 account');
  expect(loans).toHaveTextContent('1 account');
  // Each section carries only its own subtotal.
  expect(cards).toHaveTextContent(/4,820/);
  expect(loans).toHaveTextContent(/419,391/);
});

test('total owed still counts the loan', async () => {
  renderPage({ summary: WITH_LOAN });

  const summarySection = await screen.findByRole('region', { name: 'Debt summary' });
  expect(within(summarySection).getByText(/424,211/)).toBeInTheDocument();
});

test('the payoff planner schedules cards but not the loan', async () => {
  renderPage({ summary: WITH_LOAN });

  await screen.findByRole('group', { name: /mortgage 3934/i });
  expect(plannerRow()).toBeDefined();
  expect(screen.queryByText('Truist Mortgage 3934')).toBeNull();
});

test('no loans means no Loans section', async () => {
  renderPage();

  await screen.findByRole('button', { name: /^credit cards/i });
  expect(screen.queryByRole('button', { name: /^loans/i })).toBeNull();
});
