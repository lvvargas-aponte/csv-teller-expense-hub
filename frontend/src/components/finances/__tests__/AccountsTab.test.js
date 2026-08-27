import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import { MemoryRouter } from 'react-router-dom';
import AccountsTab, { createBalanceEditHandler, createDeleteManualHandler } from '../AccountsTab';
import { updateAccountBalance, deleteManualAccount } from '../../../api/balances';

jest.mock('axios');
jest.mock('../../../api/balances');
jest.mock('../../accounts/AccountsModal', () => () => <div data-testid="accounts-modal" />);

const creditAccount = (over = {}) => ({
  id: 'c1',
  institution: 'Bank of America',
  name: 'Bank of America Card',
  type: 'credit',
  available: 2011.65,
  ledger: 1488.35,
  source: 'simplefin',
  manual: false,
  ...over,
});

const summaryOf = (accounts, connections = []) => ({
  accounts,
  connections,
  cache_fetched_at: new Date().toISOString(),
});

// Account details and the classification vocabulary are the only things the
// tab fetches for itself — connection health rides along on the summary. Any
// other GET is a regression back to per-page-load provider calls, so it
// rejects loudly.
const mockApis = ({ details = {}, investmentSubtypes } = {}) => {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/accounts/details')) return Promise.resolve({ data: details });
    if (url.includes('/api/accounts/metadata')) {
      return Promise.resolve({ data: { investment_subtypes: investmentSubtypes } });
    }
    return Promise.reject(new Error(`Unexpected GET ${url}`));
  });
  axios.put.mockResolvedValue({ data: {} });
  axios.post.mockResolvedValue({ data: {} });
};

const renderTab = (accounts, opts = {}) => {
  mockApis(opts);
  return render(
    <MemoryRouter>
      <AccountsTab
        summary={summaryOf(accounts, opts.connections)}
        summaryLoading={false}
        onRefresh={jest.fn()}
      />
    </MemoryRouter>,
  );
};

beforeEach(() => jest.clearAllMocks());

// A long name, its meta line and the credit-limit/APR editing behaviour used
// to be covered here through creditAccount() rows. That markup — and the
// coverage for it — moved to DebtPage.test.js along with the credit list
// (Phase 4 Task 2). AccountsTab now only summarises and links to /debt; see
// 'credit is summarised and linked, not listed' below. (The open-date wire
// assertion did not survive that move intact — DebtPage.test.js's copy only
// checked the input's displayed value. It has since been restored to assert
// on the upsertAccountDetails payload, matching this file's original.)

test('a broken connection is announced once at the top, not per row', async () => {
  renderTab([creditAccount()], {
    connections: [{
      institution: 'Bank of America',
      status: 'disconnected',
      last_error: 'Auth failed (403)',
    }],
  });

  const strip = await screen.findByText(/needs to be reconnected/);
  expect(strip).toHaveTextContent('Bank of America');
  expect(screen.getByRole('button', { name: 'Reconnect' })).toBeInTheDocument();
});

test('healthy connections collapse to a single line', async () => {
  renderTab([creditAccount()], {
    connections: [{ institution: 'Bank of America', status: 'connected' }],
  });

  expect(await screen.findByText(/All 1 connection healthy\./)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Reconnect' })).not.toBeInTheDocument();
});

test('rendering the page makes no aggregator calls', async () => {
  // Connection health is a cached artifact of syncing. Opening the tab must
  // cost one details read and nothing else — no SimpleFIN, no SnapTrade.
  renderTab([creditAccount()], {
    connections: [{ institution: 'Bank of America', status: 'connected' }],
  });

  await screen.findByText(/All 1 connection healthy\./);
  const urls = axios.get.mock.calls.map(([url]) => url);
  expect(urls).toHaveLength(1);
  expect(urls[0]).toContain('/api/accounts/details');
});

test('credit is summarised and linked, not listed', async () => {
  renderTab([creditAccount({ name: 'Chase Sapphire' })]);

  const link = await screen.findByRole('link', { name: /debt/i });
  expect(link).toHaveAttribute('href', '/debt');
  expect(screen.queryByText(/chase sapphire/i)).toBeNull();
});

test('the payoff planner has moved to Debt', async () => {
  renderTab([creditAccount()]);
  await screen.findByRole('link', { name: /debt/i });
  expect(screen.queryByRole('heading', { name: /payoff/i })).toBeNull();
});

// One classifier, front and back: a retirement account the user tracks as a
// manual depository must group the same way here as it does on Overview and
// in the backend's totals.
const depositoryAccount = (over = {}) => ({
  id: 'd1',
  institution: 'Chase',
  name: 'Everyday Checking',
  type: 'depository',
  subtype: 'checking',
  available: 100,
  ledger: 100,
  source: 'simplefin',
  manual: false,
  ...over,
});

const section = (name) => screen.getByRole('button', { name });

test('a depository account with a retirement subtype groups under Investments', async () => {
  renderTab([
    depositoryAccount(),
    depositoryAccount({
      id: 'r1', name: 'Roth IRA', subtype: 'roth ira', available: 5000, ledger: 5000,
    }),
  ]);

  // The account itself now shows only on /invest; this page just totals it.
  await screen.findByRole('link', { name: /invest/i });

  const investments = section(/Investments/);
  expect(investments).toHaveTextContent('1 account');
  expect(investments).toHaveTextContent('$5,000.00');

  const cash = section(/Cash & savings/);
  expect(cash).toHaveTextContent('1 account');
  expect(cash).toHaveTextContent('$100.00');
  expect(cash).not.toHaveTextContent('$5,100.00');
});

// --- Real assets -----------------------------------------------------------
// A house is part of net worth and part of nothing else. Grouping it with
// cash would present $450,000 of illiquid value as spendable savings.

const assetAccount = (over = {}) => ({
  id: 'a1',
  institution: '',
  name: 'Maple Street',
  type: 'asset',
  subtype: 'home',
  available: 450000,
  ledger: 450000,
  source: 'manual',
  manual: true,
  valuation_updated_on: '2026-08-01',
  ...over,
});

const sectionNamed = async (title) => {
  const head = await screen.findByRole('button', { name: new RegExp(title) });
  return head.closest('section');
};

test('a property renders under Property & vehicles, not under Cash & savings', async () => {
  renderTab([assetAccount(), creditAccount()]);

  const assets = await sectionNamed('Property & vehicles');
  expect(within(assets).getByText('Maple Street')).toBeInTheDocument();

  const cash = await sectionNamed('Cash & savings');
  expect(within(cash).queryByText('Maple Street')).not.toBeInTheDocument();
});

test('an asset row shows the date its value was last set', async () => {
  renderTab([assetAccount({ valuation_updated_on: '2026-08-01' })]);

  const assets = await sectionNamed('Property & vehicles');
  expect(within(assets).getByText(/Valued/)).toBeInTheDocument();
});

test('a valuation older than a year is called out in words, not colour alone', async () => {
  renderTab([assetAccount({ valuation_updated_on: '2025-06-01' })]);

  const assets = await sectionNamed('Property & vehicles');
  expect(within(assets).getByText(/worth a refresh/)).toBeInTheDocument();
});

test('updating an asset value stamps the valuation date', async () => {
  const user = userEvent.setup();
  renderTab([assetAccount()]);

  const assets = await sectionNamed('Property & vehicles');
  const input = within(assets).getByLabelText(/value/i);
  await user.clear(input);
  await user.type(input, '470000');
  await user.tab();

  await waitFor(() => expect(updateAccountBalance).toHaveBeenCalledWith(
    'a1',
    expect.objectContaining({ available: 470000, ledger: 470000 }),
  ));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
    expect.stringContaining('/api/accounts/a1/details'),
    expect.objectContaining({
      valuation_updated_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    }),
  ));
});

test('an asset row shows its equity and lets a loan be linked to it', async () => {
  const user = userEvent.setup();
  renderTab([
    assetAccount({ secured_debt: 310000, equity: 140000 }),
    creditAccount({ id: 'm1', name: 'Mortgage', subtype: 'loan', ledger: 310000 }),
  ]);

  const assets = await sectionNamed('Property & vehicles');
  expect(within(assets).getByText(/\$140,000/)).toBeInTheDocument();

  const picker = within(assets).getByLabelText(/secured by/i);
  // Only credit accounts are offerable as the loan behind an asset.
  expect(within(picker).getByRole('option', { name: /Mortgage/ })).toBeInTheDocument();
  expect(within(picker).queryByRole('option', { name: /Maple Street/ })).not.toBeInTheDocument();

  await user.selectOptions(picker, 'm1');
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
    expect.stringContaining('/api/accounts/a1/details'),
    expect.objectContaining({ secured_by_account_id: 'm1' }),
  ));
});

// Collapsing the credit section to a summary (Phase 4 Task 2) must not stop
// computing creditRows — AssetRow still reads it as `creditAccounts` for this
// picker, and a task that deletes the section body along with the
// computation would silently empty this dropdown.
const houseAccount = (over = {}) => ({
  id: 'house1',
  institution: '',
  name: 'House',
  type: 'asset',
  subtype: 'home',
  available: 450000,
  ledger: 450000,
  source: 'manual',
  manual: true,
  valuation_updated_on: '2026-08-01',
  ...over,
});

test('a property can still be linked to the loan securing it', async () => {
  renderTab([houseAccount(), creditAccount({ name: 'Chase Sapphire' })]);

  const assets = await sectionNamed('Property & vehicles');
  const picker = within(assets).getByLabelText(/secured by/i);
  expect(within(picker).getByRole('option', { name: /chase sapphire/i })).toBeInTheDocument();
});

const investmentAccount = (over = {}) => ({
  id: 'i1',
  institution: 'Fidelity',
  name: 'Employer 401(k)',
  type: 'investment',
  subtype: '401k',
  available: 100000,
  ledger: 100000,
  source: 'simplefin',
  manual: false,
  tax_treatment: 'traditional',
  tax_treatment_inferred: 'traditional',
  tax_treatment_set_by_user: false,
  ...over,
});

// Per-row investment rendering — including the tax-treatment picker and its
// "assumed" marker — was retired in Phase 3 Task 3 when the Investments
// group collapsed to a summary linking to /invest. The three tests that used
// to cover that picker here (unconfirmed treatment shown as an assumption,
// confirmed treatment drops the marker, choosing a treatment saves it) are
// obsolete on this page; the holdings and their editable fields now live
// only on /invest, which has no equivalent test today.

// --- Manual-balance editing / removal --------------------------------------
// AccountsTab absorbs the two things BalancesSection alone used to offer: a
// manual account's balance can be hand-edited, and it can be removed. Neither
// is available on a synced account — its number comes from the bank feed.

const manualCashAccount = (over = {}) => ({
  id: 'mc1',
  institution: '',
  name: 'Manual Cash',
  type: 'depository',
  subtype: 'checking',
  available: 500,
  ledger: 500,
  source: 'manual',
  manual: true,
  ...over,
});

const syncedCashAccount = (over = {}) => ({
  id: 'sc1',
  institution: 'Chase',
  name: 'Chase Checking',
  type: 'depository',
  subtype: 'checking',
  available: 1200,
  ledger: 1200,
  source: 'simplefin',
  manual: false,
  ...over,
});

function renderAccountsTab(props = {}) {
  const { accounts, onRefresh, ...opts } = props;
  mockApis(opts);
  return render(
    <MemoryRouter>
      <AccountsTab
        summary={summaryOf(accounts || [manualCashAccount(), syncedCashAccount()], opts.connections)}
        summaryLoading={false}
        onRefresh={onRefresh || jest.fn()}
      />
    </MemoryRouter>,
  );
}

test('a manual account can have its balance edited', async () => {
  const user = userEvent.setup();
  renderAccountsTab();

  const row = await screen.findByRole('group', { name: /manual cash/i });
  await user.click(within(row).getByRole('button', { name: /edit balance/i }));
  await user.clear(within(row).getByLabelText(/available/i));
  await user.type(within(row).getByLabelText(/available/i), '250');
  await user.click(within(row).getByRole('button', { name: /save/i }));

  expect(updateAccountBalance).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({ available: 250 }),
  );
});

// FIX 1 — the editor must pre-fill the *starting* balance (what the PUT
// writes back into), not the live computed one (starting - linked-txn
// delta). Seeding from the computed value made an unchanged save walk the
// stored balance down by the delta on every save.
test("a manual account's balance editor pre-fills the starting balance, not the live computed one", async () => {
  const user = userEvent.setup();
  renderAccountsTab({
    accounts: [manualCashAccount({
      available: 950, ledger: 950, starting_balance: 1000, txn_delta: -50, linked_txn_count: 3,
    })],
  });

  const row = await screen.findByRole('group', { name: /manual cash/i });
  // The row itself still shows the live, computed number.
  expect(within(row).getByText('$950.00')).toBeInTheDocument();

  await user.click(within(row).getByRole('button', { name: /edit balance/i }));
  expect(within(row).getByLabelText(/available/i)).toHaveValue(1000);
  expect(within(row).getByText(/from 3 linked txns/i)).toBeInTheDocument();

  await user.click(within(row).getByRole('button', { name: /save/i }));

  expect(updateAccountBalance).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({ available: 1000 }),
  );
});

// FIX 5 — a failing save must keep the editor open and show the error,
// rather than closing (losing the edit) and failing silently.
test('a failed balance save keeps the editor open and shows an error', async () => {
  const user = userEvent.setup();
  updateAccountBalance.mockRejectedValueOnce({ response: { data: { detail: 'Simulated failure' } } });
  renderAccountsTab();

  const row = await screen.findByRole('group', { name: /manual cash/i });
  await user.click(within(row).getByRole('button', { name: /edit balance/i }));
  await user.click(within(row).getByRole('button', { name: /save/i }));

  expect(await within(row).findByText(/simulated failure/i)).toBeInTheDocument();
  expect(within(row).getByLabelText(/available/i)).toBeInTheDocument();
});

// A follow-up finding: routing this failure into localError (which also
// feeds ConnectionsStrip's syncError prop) mislabelled a balance-entry
// mistake as a bank-connection problem. The row's own saveError is the
// only place this belongs — the connections strip must show no error and
// no attention state.
test('a failed balance save does not mark the connections strip as needing attention', async () => {
  const user = userEvent.setup();
  updateAccountBalance.mockRejectedValueOnce({ response: { data: { detail: 'Simulated failure' } } });
  renderAccountsTab();

  const row = await screen.findByRole('group', { name: /manual cash/i });
  await user.click(within(row).getByRole('button', { name: /edit balance/i }));
  await user.click(within(row).getByRole('button', { name: /save/i }));
  await within(row).findByText(/simulated failure/i);

  // The error appears exactly once — inside the row — not a second time in
  // the connections strip.
  expect(screen.getAllByText(/simulated failure/i)).toHaveLength(1);
  expect(screen.getByText(/no banks connected yet/i)).toBeInTheDocument();
  expect(screen.queryByText(/sync failed/i)).toBeNull();
});

// FIX 2(a) — most users are SimpleFIN-only. SnapTrade must not even be
// called (POST /api/snaptrade/sync answers 503/409 for such a user), or a
// fully successful sync would report an error every time.
test('Sync all does not call SnapTrade when there are no investment accounts', async () => {
  const user = userEvent.setup();
  renderAccountsTab({ accounts: [manualCashAccount(), syncedCashAccount()] });

  await screen.findByRole('group', { name: /manual cash/i });
  await user.click(screen.getByRole('button', { name: /sync all/i }));

  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining('/api/simplefin/sync'),
    expect.anything(),
  ));
  const urls = axios.post.mock.calls.map(([url]) => url);
  expect(urls.some((u) => u.includes('/api/snaptrade/sync'))).toBe(false);
  expect(screen.queryByText(/sync failed/i)).toBeNull();
});

test('a synced account offers no balance editing', async () => {
  renderAccountsTab();

  const row = await screen.findByRole('group', { name: /chase/i });
  expect(within(row).queryByRole('button', { name: /edit balance/i })).toBeNull();
});

test('deleting a manual account asks first', async () => {
  const user = userEvent.setup();
  jest.spyOn(window, 'confirm').mockReturnValue(false);
  renderAccountsTab();

  const row = await screen.findByRole('group', { name: /manual cash/i });
  await user.click(within(row).getByRole('button', { name: /remove/i }));

  expect(window.confirm).toHaveBeenCalled();
  expect(deleteManualAccount).not.toHaveBeenCalled();
  window.confirm.mockRestore();
});

// The row hides the control for a synced account (covered above), but that's
// only the first line of defence. This calls AccountsTab's real handlers
// directly — bypassing the row and its button entirely — the way a bypassed
// row or a future caller could, and proves the handler itself refuses.
test('the balance-edit handler refuses a non-manual account, even called directly', async () => {
  const update = jest.fn();
  const refresh = jest.fn();
  const handler = createBalanceEditHandler(update, refresh);

  await handler('sc1', false, { available: 999, ledger: 999 });

  expect(update).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});

test('investments are summarised, not listed twice', async () => {
  renderAccountsTab({ accounts: [investmentAccount(), manualCashAccount()] });

  const link = await screen.findByRole('link', { name: /invest/i });
  expect(link).toHaveAttribute('href', '/invest');
  // The holdings themselves belong to /invest; the section header above
  // still shows the total, so the link doesn't repeat it.
  expect(screen.queryByText(/employer 401\(k\)/i)).toBeNull();
});

// The "paid off" text badge and the zero-balance-not-filtered behaviour it
// covers are still exercised, now on DebtPage.test.js, where the rows that
// carry that markup live.

test('the delete handler refuses a non-manual account, even called directly', async () => {
  jest.spyOn(window, 'confirm');
  const del = jest.fn();
  const refresh = jest.fn();
  const onError = jest.fn();
  const handler = createDeleteManualHandler(del, refresh, onError);

  await handler('sc1', false, 'Chase Checking');

  // Bails before even asking — a synced account should never get as far as
  // the confirmation prompt.
  expect(window.confirm).not.toHaveBeenCalled();
  expect(del).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();

  window.confirm.mockRestore();
});
