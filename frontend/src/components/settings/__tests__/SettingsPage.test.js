import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from '../SettingsPage';
import { getProfile, updateProfile } from '../../../api/profile';
import { getCategoryRules, replaceCategoryRules } from '../../../api/categoryRules';

jest.mock('../../../api/profile');
jest.mock('../../../api/categoryRules');
// The connections pane can open the accounts modal, which fetches on mount.
jest.mock('../../accounts/AccountsModal', () => () => <div>accounts modal</div>);

const EMPTY_PROFILE = {
  risk_tolerance: null, time_horizon_years: null, dependents: null,
  debt_strategy: null, monthly_income: null, emergency_fund_months: null,
  notes: '', updated_at: null,
};

const health = {
  institutions: [
    { institution: 'Chase', status: 'connected', last_error: null },
    { institution: 'Bank of America', status: 'disconnected', last_error: 'Login required' },
    { institution: 'Discover', status: 'manual', last_error: null },
  ],
  broken: [{ institution: 'Bank of America', status: 'disconnected', last_error: 'Login required' }],
  connected: [{ institution: 'Chase', status: 'connected', last_error: null }],
};

const summary = {
  accounts: [
    { id: 'a1', institution: 'Chase', name: 'Total Checking' },
    { id: 'a2', institution: 'Chase', name: 'Prime Visa' },
    { id: 'a3', institution: 'Bank of America', name: 'Cash Rewards' },
  ],
};

function renderPage(props = {}) {
  return render(
    <SettingsPage
      health={health}
      summary={summary}
      categories={['Groceries', 'Transport']}
      categoryCounts={{ Groceries: 42, Transport: 18 }}
      {...props}
    />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  getProfile.mockResolvedValue({ data: EMPTY_PROFILE });
  getCategoryRules.mockResolvedValue({ data: [] });
  updateProfile.mockResolvedValue({ data: EMPTY_PROFILE });
  replaceCategoryRules.mockResolvedValue({ data: [] });
});

const awaitLoad = () => screen.findByRole('heading', { name: /financial profile/i });

test('opens on the financial profile pane', async () => {
  renderPage();
  expect(await awaitLoad()).toBeInTheDocument();
  expect(screen.getByText(/shape the recommendations/i)).toBeInTheDocument();
});

test('deep-links straight to the connections pane', async () => {
  renderPage({ initialPane: 'connections' });
  expect(
    await screen.findByRole('heading', { name: /connected institutions/i }),
  ).toBeInTheDocument();
});

test('no save bar until something actually changes', async () => {
  renderPage();
  await awaitLoad();
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
});

test('editing raises the save bar and restoring the old value lowers it', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();

  const dependents = screen.getByLabelText('Dependents');
  await user.type(dependents, '2');
  expect(await screen.findByText('Unsaved changes')).toBeInTheDocument();

  await user.clear(dependents);
  await waitFor(() =>
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument());
});

test('unsaved edits survive switching tabs and save together', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();

  await user.type(screen.getByLabelText('Dependents'), '3');
  await user.click(screen.getByRole('tab', { name: /categories & rules/i }));
  expect(await screen.findByRole('heading', { name: /categories & rules/i })).toBeInTheDocument();
  // The bar follows the page, not the pane.
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument();

  await user.click(screen.getByRole('tab', { name: /financial profile/i }));
  expect(await screen.findByLabelText('Dependents')).toHaveValue(3);
});

test('save sends cleared fields as null so "Not set" actually unsets', async () => {
  const user = userEvent.setup();
  getProfile.mockResolvedValue({
    data: { ...EMPTY_PROFILE, debt_strategy: 'avalanche', dependents: 2 },
  });
  renderPage();
  await awaitLoad();

  await user.selectOptions(screen.getByLabelText('Debt-payoff strategy'), '');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => expect(updateProfile).toHaveBeenCalled());
  expect(updateProfile.mock.calls[0][0]).toMatchObject({
    debt_strategy: null,
    dependents: 2,
  });
});

test('save shows a toast and clears the bar', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();

  await user.type(screen.getByLabelText('Dependents'), '1');
  updateProfile.mockResolvedValue({ data: { ...EMPTY_PROFILE, dependents: 1 } });
  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  expect(await screen.findByText(/settings saved/i)).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument());
});

test('a failed save keeps the bar up and reports why', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();

  await user.type(screen.getByLabelText('Dependents'), '1');
  updateProfile.mockRejectedValue(new Error('boom'));
  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  expect(await screen.findByText(/could not save settings/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
  expect(screen.queryByText(/settings saved/i)).not.toBeInTheDocument();
});

test('discard restores the last saved values', async () => {
  const user = userEvent.setup();
  getProfile.mockResolvedValue({ data: { ...EMPTY_PROFILE, dependents: 2 } });
  renderPage();
  await awaitLoad();

  const dependents = screen.getByLabelText('Dependents');
  await user.clear(dependents);
  await user.type(dependents, '7');
  await user.click(await screen.findByRole('button', { name: 'Discard' }));

  await waitFor(() => expect(dependents).toHaveValue(2));
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
});

test('the connections tab flags institutions needing attention', async () => {
  renderPage();
  await awaitLoad();
  const item = screen.getByRole('tab', { name: /connected institutions/i });
  expect(within(item).getByLabelText('needs attention')).toBeInTheDocument();
});

test('a broken connection points at SimpleFIN Bridge rather than a dead button', async () => {
  renderPage({ initialPane: 'connections' });
  await screen.findByRole('heading', { name: /connected institutions/i });

  expect(screen.getByText(/reconnect needed/i)).toBeInTheDocument();
  expect(screen.getByText(/SimpleFIN Bridge account/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Reconnect$/ })).not.toBeInTheDocument();
});

test('removing an institution warns that history is kept, and detaches on confirm', async () => {
  const user = userEvent.setup();
  const axios = require('axios');
  jest.spyOn(axios, 'delete').mockResolvedValue({ data: {} });

  renderPage({ initialPane: 'connections' });
  await screen.findByRole('heading', { name: /connected institutions/i });

  const chaseRow = screen.getByRole('group', { name: 'Chase' });
  await user.click(within(chaseRow).getByRole('button', { name: 'Remove' }));

  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText(/past transactions are kept/i)).toBeInTheDocument();

  await user.click(within(dialog).getByRole('button', { name: 'Remove' }));
  // One call per account behind the institution.
  await waitFor(() => expect(axios.delete).toHaveBeenCalledTimes(2));
});

test('category chips show live transaction counts', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();
  await user.click(screen.getByRole('tab', { name: /categories & rules/i }));

  expect(await screen.findByText('Groceries')).toBeInTheDocument();
  expect(screen.getByText('42')).toBeInTheDocument();
  expect(screen.getByText('18')).toBeInTheDocument();
});

test('adding a rule marks the page dirty and saves the ordered list', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();
  await user.click(screen.getByRole('tab', { name: /categories & rules/i }));

  await user.click(await screen.findByRole('button', { name: '+ Add rule' }));
  await user.type(screen.getByLabelText('Merchant text to match'), 'TRADER JOE');
  await user.selectOptions(screen.getByLabelText('Category to apply'), 'Groceries');

  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => expect(replaceCategoryRules).toHaveBeenCalledWith([
    { match: 'TRADER JOE', category: 'Groceries' },
  ]));
});

test('blank rules are not sent', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();
  await user.click(screen.getByRole('tab', { name: /categories & rules/i }));

  await user.click(await screen.findByRole('button', { name: '+ Add rule' }));
  await user.type(screen.getByLabelText('Merchant text to match'), 'UBER');
  await user.click(screen.getByRole('button', { name: '+ Add rule' }));

  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => expect(replaceCategoryRules).toHaveBeenCalledWith([
    { match: 'UBER', category: 'Groceries' },
  ]));
});

test('a load failure offers a retry instead of an empty form', async () => {
  getProfile.mockRejectedValue(new Error('down'));
  renderPage();
  expect(await screen.findByText(/could not load settings/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
});

test('the marginal rate and the after-tax toggle save together', async () => {
  const user = userEvent.setup();
  renderPage();
  await awaitLoad();

  await user.type(screen.getByLabelText(/marginal tax rate/i), '22');
  await user.click(screen.getByLabelText(/show after-tax net worth/i));
  await user.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => expect(updateProfile).toHaveBeenCalledWith(
    expect.objectContaining({
      marginal_tax_rate_pct: 22,
      show_after_tax_net_worth: true,
    }),
  ));
});

test('the after-tax toggle is off until the user turns it on', async () => {
  renderPage();
  await awaitLoad();

  expect(screen.getByLabelText(/show after-tax net worth/i)).not.toBeChecked();
});
