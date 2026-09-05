import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from '../SettingsPage';
import { getProfile, updateProfile } from '../../../api/profile';
import {
  getCategoryRules, patchCategoryRule, deleteCategoryRule, createCategoryRule,
} from '../../../api/categoryRules';
import {
  listCategoryRows, createCategory, patchCategory, renameCategory, mergeCategory,
  deleteCategoryById, setCategoryParent,
} from '../../../api/categories';

jest.mock('../../../api/profile');
jest.mock('../../../api/categoryRules');
jest.mock('../../../api/categories');

const EMPTY_PROFILE = {
  risk_tolerance: null, time_horizon_years: null, dependents: null,
  debt_strategy: null, monthly_income: null, emergency_fund_months: null,
  notes: '', updated_at: null,
};

function renderPage(props = {}) {
  return render(
    <SettingsPage {...props} />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  getProfile.mockResolvedValue({ data: EMPTY_PROFILE });
  getCategoryRules.mockResolvedValue({ data: [] });
  updateProfile.mockResolvedValue({ data: EMPTY_PROFILE });
  listCategoryRows.mockResolvedValue({
    data: { rows: [], categories: [], counts: {}, spend: {} },
  });
});

const awaitLoad = () => screen.findByRole('heading', { name: /financial profile/i });

test('opens on the financial profile pane', async () => {
  renderPage();
  expect(await awaitLoad()).toBeInTheDocument();
  expect(screen.getByText(/shape the recommendations/i)).toBeInTheDocument();
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

test('does not report dirty state upward any more', async () => {
  const onDirtyChange = jest.fn();
  const user = userEvent.setup();
  renderPage({ onDirtyChange });

  await user.type(await screen.findByLabelText('Dependents'), '3');
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument();

  // The prop is gone; a stray caller must not silently keep working.
  expect(onDirtyChange).not.toHaveBeenCalled();
});

test('still guards a browser-level exit while dirty', async () => {
  const addSpy = jest.spyOn(window, 'addEventListener');
  const user = userEvent.setup();
  renderPage();

  await user.type(await screen.findByLabelText('Dependents'), '3');

  expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function));
  addSpy.mockRestore();
});

test('connections are managed on the Accounts page, not here', async () => {
  renderPage();

  expect(await screen.findByRole('tab', { name: /financial profile/i })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /categories/i })).toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /connected institutions/i })).toBeNull();
});

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

test('the settings tabs carry no emoji', () => {
  const { container } = renderPage();
  expect(container.textContent).not.toMatch(EMOJI);
});
