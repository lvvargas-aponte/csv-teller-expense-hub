import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import AccountsTab from '../AccountsTab';

jest.mock('axios');
jest.mock('../../accounts/AccountsModal', () => () => <div data-testid="accounts-modal" />);

const LONG_NAME = 'Customized Cash Rewards Visa Signature 7473';

const creditAccount = (over = {}) => ({
  id: 'c1',
  institution: 'Bank of America',
  name: LONG_NAME,
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
};

const renderTab = (accounts, opts = {}) => {
  mockApis(opts);
  return render(
    <AccountsTab
      summary={summaryOf(accounts, opts.connections)}
      summaryLoading={false}
      onRefresh={jest.fn()}
    />,
  );
};

// Each expandable account row is a button whose accessible name carries the
// account name, so we can address a row without reaching into the DOM.
const findRow = (name) => screen.findByRole('button', { name: new RegExp(name) });

beforeEach(() => jest.clearAllMocks());

test('a long account name renders in full, with no truncation', async () => {
  renderTab([creditAccount()]);

  const row = await findRow(LONG_NAME);
  // The old table clipped names with text-overflow; the row must not.
  expect(within(row).getByText(LONG_NAME)).toBeInTheDocument();
});

test('empty metadata is omitted from the meta line rather than shown as dashes', async () => {
  renderTab([creditAccount()], { details: {} });

  const row = await findRow(LONG_NAME);
  expect(row).toHaveTextContent('Bank of America');
  expect(row).not.toHaveTextContent('—');
  expect(row).not.toHaveTextContent(/APR|used|due day|min \$/);
});

test('populated metadata appears in the meta line', async () => {
  renderTab([creditAccount()], {
    details: { c1: { credit_limit: 3500, apr: 21.99, minimum_payment: 37 } },
  });

  const row = await findRow(LONG_NAME);
  expect(row).toHaveTextContent('43% used');
  expect(row).toHaveTextContent('21.99% APR');
  expect(row).toHaveTextContent('min $37.00');
});

test('editing the credit limit on a manual card recomputes its available credit', async () => {
  const user = userEvent.setup();
  renderTab(
    [creditAccount({ id: 'm1', name: 'Discover', manual: true, ledger: 1000, available: 0 })],
    { details: { m1: { credit_limit: 4000 } } },
  );

  const row = await findRow('Discover');
  expect(within(row).getByText('$3,000.00 available')).toBeInTheDocument();

  await user.click(row);
  const limitInput = screen.getByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '5000');
  await user.tab();

  await waitFor(() => {
    expect(within(row).getByText('$4,000.00 available')).toBeInTheDocument();
  });
  expect(axios.put).toHaveBeenCalled();
});

test("a synced card keeps the bank's available credit when the limit is edited", async () => {
  const user = userEvent.setup();
  renderTab([creditAccount({ available: 2011.65, ledger: 1488.35 })], {
    details: { c1: { credit_limit: 3500 } },
  });

  const row = await findRow(LONG_NAME);
  await user.click(row);
  const limitInput = screen.getByPlaceholderText('$ limit');
  await user.clear(limitInput);
  await user.type(limitInput, '9000');
  await user.tab();

  await waitFor(() => expect(axios.put).toHaveBeenCalled());
  // Utilization follows the new limit, but availability stays the bank's number.
  expect(within(row).getByText('$2,011.65 available')).toBeInTheDocument();
  expect(row).toHaveTextContent('17% used');
});

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

  const row = await findRow(LONG_NAME);
  expect(row).toHaveTextContent('needs reconnect');
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

  await screen.findByText('Roth IRA');

  const investments = section(/Investments/);
  expect(investments).toHaveTextContent('1 account');
  expect(investments).toHaveTextContent('$5,000.00');

  const cash = section(/Cash & savings/);
  expect(cash).toHaveTextContent('1 account');
  expect(cash).toHaveTextContent('$100.00');
  expect(cash).not.toHaveTextContent('$5,100.00');
});
