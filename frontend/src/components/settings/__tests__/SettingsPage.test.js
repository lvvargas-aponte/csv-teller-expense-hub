import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from '../SettingsPage';
import { getProfile, updateProfile } from '../../../api/profile';
import {
  getCategoryRules, replaceCategoryRules, patchCategoryRule, deleteCategoryRule,
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
    <SettingsPage
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
  listCategoryRows.mockResolvedValue({ data: { rows: [], categories: [], counts: {} } });
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

test('category rows show live transaction counts', async () => {
  const user = userEvent.setup();
  listCategoryRows.mockResolvedValue({
    data: {
      rows: [
        { id: 1, name: 'Groceries', color: null, roles: [], archived: false, sort: 0 },
        { id: 2, name: 'Transport', color: null, roles: [], archived: false, sort: 1 },
      ],
      categories: ['Groceries', 'Transport'],
      counts: { Groceries: 42, Transport: 18 },
    },
  });
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
    { pattern: 'TRADER JOE', category: 'Groceries' },
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
    { pattern: 'UBER', category: 'Groceries' },
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

describe('merchant rules learned from transactions', () => {
  const LEARNED = {
    id: 7, kind: 'merchant', pattern: 'chipotle', category: 'Dining',
    position: 0, enabled: true, created_at: null, last_matched_at: null,
  };

  test('lists them separately from the substring rules', async () => {
    getCategoryRules.mockResolvedValue({ data: [LEARNED] });
    render(<SettingsPage initialPane="categories" categories={['Dining']} />);
    expect(await screen.findByText('chipotle')).toBeInTheDocument();
    expect(screen.getByText('Learned from your transactions')).toBeInTheDocument();
  });

  test('a merchant rule is not editable as a substring rule', async () => {
    // The PUT deliberately leaves merchant rules alone, so drafting one into
    // that form would resurrect it as a duplicate `contains` rule on save.
    getCategoryRules.mockResolvedValue({ data: [LEARNED] });
    render(<SettingsPage initialPane="categories" categories={['Dining']} />);
    await screen.findByText('chipotle');
    expect(screen.queryByLabelText('Merchant text to match')).not.toBeInTheDocument();
  });

  test('turning one off patches it immediately rather than waiting for Save', async () => {
    const user = userEvent.setup();
    getCategoryRules.mockResolvedValue({ data: [LEARNED] });
    patchCategoryRule.mockResolvedValue({ data: { ...LEARNED, enabled: false } });
    render(<SettingsPage initialPane="categories" categories={['Dining']} />);
    await screen.findByText('chipotle');

    await user.click(screen.getByRole('checkbox', { name: 'Rule for chipotle is on' }));

    await waitFor(() => expect(patchCategoryRule).toHaveBeenCalledWith(7, { enabled: false }));
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  test('deleting one calls the per-row endpoint', async () => {
    const user = userEvent.setup();
    getCategoryRules.mockResolvedValue({ data: [LEARNED] });
    deleteCategoryRule.mockResolvedValue({ data: { deleted: 7 } });
    render(<SettingsPage initialPane="categories" categories={['Dining']} />);
    await screen.findByText('chipotle');

    await user.click(screen.getByRole('button', { name: 'Delete rule for chipotle' }));

    await waitFor(() => expect(deleteCategoryRule).toHaveBeenCalledWith(7));
  });

  test('says so when nothing has been learned yet', async () => {
    getCategoryRules.mockResolvedValue({ data: [] });
    render(<SettingsPage initialPane="categories" categories={['Dining']} />);
    expect(await screen.findByText(/Nothing learned yet/)).toBeInTheDocument();
  });
});

describe('editing categories', () => {
  const ROWS = [
    { id: 1, name: 'Groceries', color: null, roles: [], archived: false, sort: 0 },
    { id: 2, name: 'Subscriptions', color: null, roles: ['bill', 'subscription'], archived: false, sort: 1 },
  ];

  async function openCategories(rows = ROWS) {
    const user = userEvent.setup();
    listCategoryRows.mockResolvedValue({
      data: { rows, categories: rows.map((r) => r.name), counts: {} },
    });
    renderPage();
    await awaitLoad();
    await user.click(screen.getByRole('tab', { name: /categories & rules/i }));
    await screen.findByText('Groceries');
    return user;
  }

  test('renaming commits against the server rather than the Save bar', async () => {
    // A rename rewrites every transaction, budget and rule that used the old
    // name — there is no coherent "discard" for that.
    const user = await openCategories();
    renameCategory.mockResolvedValue({ data: { ...ROWS[0], name: 'Food' } });

    await user.click(screen.getByRole('button', { name: 'Groceries' }));
    const input = screen.getByLabelText('Rename Groceries');
    await user.clear(input);
    await user.type(input, 'Food{Enter}');

    await waitFor(() => expect(renameCategory).toHaveBeenCalledWith(1, 'Food'));
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  test('renaming to the same name does not call the server', async () => {
    const user = await openCategories();
    await user.click(screen.getByRole('button', { name: 'Groceries' }));
    await user.click(document.body);
    expect(renameCategory).not.toHaveBeenCalled();
  });

  test('shows the roles that drive how a category is treated', async () => {
    await openCategories();
    expect(screen.getByText('Bill')).toBeInTheDocument();
    expect(screen.getByText('Subscription')).toBeInTheDocument();
  });

  test('a role can be toggled on', async () => {
    const user = await openCategories();
    patchCategory.mockResolvedValue({ data: ROWS[0] });

    await user.click(screen.getByRole('button', { name: 'Options for Groceries' }));
    await user.click(screen.getByRole('checkbox', { name: 'Not spending' }));

    await waitFor(() => expect(patchCategory).toHaveBeenCalledWith(1, { roles: ['non_spending'] }));
  });

  test('merging folds one category into another', async () => {
    const user = await openCategories();
    mergeCategory.mockResolvedValue({ data: ROWS[1] });

    await user.click(screen.getByRole('button', { name: 'Options for Groceries' }));
    await user.selectOptions(
      screen.getByLabelText('Merge Groceries into another category'), '2',
    );

    await waitFor(() => expect(mergeCategory).toHaveBeenCalledWith(1, 2));
  });

  test('archiving is offered as the non-destructive option', async () => {
    const user = await openCategories();
    patchCategory.mockResolvedValue({ data: { ...ROWS[0], archived: true } });

    await user.click(screen.getByRole('button', { name: 'Options for Groceries' }));
    await user.click(screen.getByRole('button', { name: 'Archive' }));

    await waitFor(() => expect(patchCategory).toHaveBeenCalledWith(1, { archived: true }));
  });

  test('deleting asks first, because no undo puts the labels back', async () => {
    const user = await openCategories();
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(false);

    await user.click(screen.getByRole('button', { name: 'Options for Groceries' }));
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(deleteCategoryById).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  test('deleting proceeds once confirmed', async () => {
    const user = await openCategories();
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(true);
    deleteCategoryById.mockResolvedValue({ data: { removed: 'Groceries' } });

    await user.click(screen.getByRole('button', { name: 'Options for Groceries' }));
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteCategoryById).toHaveBeenCalledWith(1));
    confirmSpy.mockRestore();
  });

  test('adding a category creates it', async () => {
    const user = await openCategories();
    createCategory.mockResolvedValue({ data: { id: 3, name: 'Pets', roles: [] } });

    await user.type(screen.getByLabelText('New category name'), 'Pets');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(createCategory).toHaveBeenCalledWith('Pets'));
  });

  test('archived categories are hidden until asked for', async () => {
    const user = await openCategories();
    await user.click(screen.getByRole('checkbox', { name: 'Show archived' }));
    await waitFor(() => expect(listCategoryRows).toHaveBeenCalledWith(true));
  });
});

describe('grouping categories', () => {
  const GROUPED = [
    { id: 1, name: 'Food', color: null, roles: [], archived: false, sort: 0, parent_id: null },
    { id: 2, name: 'Groceries', color: null, roles: [], archived: false, sort: 1, parent_id: 1 },
    { id: 3, name: 'Gas', color: null, roles: [], archived: false, sort: 2, parent_id: null },
  ];

  async function openCategories(rows = GROUPED) {
    const user = userEvent.setup();
    listCategoryRows.mockResolvedValue({
      data: { rows, categories: rows.map((r) => r.name), counts: {} },
    });
    renderPage();
    await awaitLoad();
    await user.click(screen.getByRole('tab', { name: /categories & rules/i }));
    await screen.findByText('Food');
    return user;
  }

  test('shows which parent a category rolls into', async () => {
    await openCategories();
    expect(screen.getByText('↳ Food')).toBeInTheDocument();
  });

  test('shows how many a parent holds', async () => {
    await openCategories();
    expect(screen.getByText('1 inside')).toBeInTheDocument();
  });

  test('grouping one category under another calls the endpoint', async () => {
    const user = await openCategories();
    setCategoryParent.mockResolvedValue({ data: { ...GROUPED[2], parent_id: 1 } });

    await user.click(screen.getByRole('button', { name: 'Options for Gas' }));
    await user.selectOptions(
      screen.getByLabelText('Group Gas under another category'), '1',
    );

    await waitFor(() => expect(setCategoryParent).toHaveBeenCalledWith(3, 1));
  });

  test('ungrouping passes a null parent', async () => {
    const user = await openCategories();
    setCategoryParent.mockResolvedValue({ data: { ...GROUPED[1], parent_id: null } });

    await user.click(screen.getByRole('button', { name: 'Options for Groceries' }));
    await user.selectOptions(
      screen.getByLabelText('Group Groceries under another category'), '',
    );

    await waitFor(() => expect(setCategoryParent).toHaveBeenCalledWith(2, null));
  });

  test('a category that already holds others cannot be nested', async () => {
    // Grouping is one level deep, so the picker refuses rather than letting
    // the server 422 after the click.
    const user = await openCategories();
    await user.click(screen.getByRole('button', { name: 'Options for Food' }));
    expect(screen.getByLabelText('Group Food under another category')).toBeDisabled();
  });

  test('a grouped category is not offered as a parent', async () => {
    const user = await openCategories();
    await user.click(screen.getByRole('button', { name: 'Options for Gas' }));
    const options = Array.from(
      screen.getByLabelText('Group Gas under another category').options,
    ).map((o) => o.textContent);
    expect(options).toContain('Food');
    expect(options).not.toContain('Groceries');
  });
});
