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

const ROWS = [
  { id: 1, name: 'Food', color: null, roles: [], archived: false, sort: 0, parent_id: null },
  { id: 2, name: 'Groceries', color: null, roles: [], archived: false, sort: 1, parent_id: 1 },
  { id: 3, name: 'Subscriptions', color: null, roles: ['bill', 'subscription'], archived: false, sort: 2, parent_id: null },
];

const RULES = [
  { id: 11, kind: 'merchant', pattern: 'trader joe', category: 'Groceries', enabled: true, position: 0, last_matched_at: null },
  { id: 12, kind: 'contains', pattern: 'ALDI', category: 'Groceries', enabled: true, position: 1, last_matched_at: null },
  { id: 13, kind: 'contains', pattern: 'NETFLIX', category: 'Subscriptions', enabled: false, position: 2, last_matched_at: null },
];

beforeEach(() => {
  jest.clearAllMocks();
  getProfile.mockResolvedValue({ data: EMPTY_PROFILE });
  updateProfile.mockResolvedValue({ data: EMPTY_PROFILE });
});

async function openPane({ rows = ROWS, rules = RULES } = {}) {
  const user = userEvent.setup();
  listCategoryRows.mockResolvedValue({
    data: {
      rows,
      categories: rows.map((r) => r.name),
      counts: { Food: 143, Groceries: 62, Subscriptions: 31 },
      spend: { Food: 1204, Groceries: 612, Subscriptions: 264 },
    },
  });
  getCategoryRules.mockResolvedValue({ data: rules });
  render(<SettingsPage />);
  await screen.findByRole('heading', { name: /financial profile/i });
  await user.click(screen.getByRole('tab', { name: /categories & rules/i }));
  await screen.findByRole('button', { name: 'Groceries' });
  return user;
}

const expand = (user, name) =>
  user.click(screen.getByRole('button', { name }));

describe('the list', () => {
  test('shows each category with its count and month spend', async () => {
    await openPane();
    expect(screen.getByText('62')).toBeInTheDocument();
    expect(screen.getByText('$612.00')).toBeInTheDocument();
  });

  test('a category carries the rules that pick it, not a separate list', async () => {
    const user = await openPane();
    // Collapsed, the row only says how many; the patterns live inside it.
    expect(screen.getByText('2 rules')).toBeInTheDocument();
    expect(screen.queryByText('trader joe')).not.toBeInTheDocument();

    await expand(user, 'Groceries');
    expect(screen.getByText('trader joe')).toBeInTheDocument();
    expect(screen.getByText('ALDI')).toBeInTheDocument();
  });

  test('filtering matches a rule pattern, not just the category name', async () => {
    // Searching a merchant should find the category it feeds.
    const user = await openPane();
    await user.type(screen.getByLabelText('Filter categories and rules'), 'trader');

    expect(screen.getByRole('button', { name: 'Groceries' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Subscriptions' })).not.toBeInTheDocument();
  });

  test('says when nothing matches', async () => {
    const user = await openPane();
    await user.type(screen.getByLabelText('Filter categories and rules'), 'zzzz');
    expect(screen.getByText('Nothing matches that.')).toBeInTheDocument();
  });

  test('archived categories are hidden until asked for', async () => {
    const user = await openPane();
    await user.click(screen.getByRole('checkbox', { name: 'Archived' }));
    await waitFor(() => expect(listCategoryRows).toHaveBeenCalledWith(true));
  });
});

describe('rules inside a category', () => {
  test('only text rules are numbered, because merchant rules always run first', async () => {
    // First match wins, so order decides the answer — but a merchant rule's
    // position is not a choice, and numbering it would say it was.
    const user = await openPane();
    await expand(user, 'Groceries');
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('1.')).toBeInTheDocument();
  });

  test('says so when a category has no rules yet', async () => {
    const user = await openPane();
    await expand(user, 'Food');
    expect(screen.getByText(/No rules yet/)).toBeInTheDocument();
  });

  test('adding a text rule files it under that category', async () => {
    const user = await openPane();
    createCategoryRule.mockResolvedValue({ data: { rule: {} } });
    await expand(user, 'Groceries');

    await user.type(screen.getByLabelText('New text rule for Groceries'), 'WHOLE FOODS');
    await user.click(screen.getByRole('button', { name: 'Add text rule' }));

    await waitFor(() => expect(createCategoryRule).toHaveBeenCalledWith(
      'WHOLE FOODS', 'Groceries', { kind: 'contains' },
    ));
  });

  test('a rule can be switched off without losing what it says', async () => {
    const user = await openPane();
    patchCategoryRule.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    await user.click(screen.getByRole('checkbox', { name: 'Rule trader joe is on' }));

    await waitFor(() => expect(patchCategoryRule).toHaveBeenCalledWith(11, { enabled: false }));
  });

  test('a rule can be deleted', async () => {
    const user = await openPane();
    deleteCategoryRule.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    await user.click(screen.getByRole('button', { name: 'Delete rule ALDI' }));

    await waitFor(() => expect(deleteCategoryRule).toHaveBeenCalledWith(12));
  });
});

describe('editing a category', () => {
  test('renaming commits against the server rather than the save bar', async () => {
    // A rename rewrites every transaction, budget and rule that used the old
    // name — there is no coherent "discard" for that.
    const user = await openPane();
    renameCategory.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    const input = screen.getByDisplayValue('Groceries');
    await user.clear(input);
    await user.type(input, 'Food shopping');
    await user.tab();

    await waitFor(() => expect(renameCategory).toHaveBeenCalledWith(2, 'Food shopping'));
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  test('renaming to the same name does not call the server', async () => {
    const user = await openPane();
    await expand(user, 'Groceries');
    await user.click(screen.getByDisplayValue('Groceries'));
    await user.tab();
    expect(renameCategory).not.toHaveBeenCalled();
  });

  test('shows the roles that change how a category is treated', async () => {
    await openPane();
    expect(screen.getByText('Bill')).toBeInTheDocument();
    expect(screen.getByText('Subscription')).toBeInTheDocument();
  });

  test('a role can be toggled on', async () => {
    const user = await openPane();
    patchCategory.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    await user.click(screen.getByRole('checkbox', { name: 'Not spending — Groceries' }));

    await waitFor(() => expect(patchCategory).toHaveBeenCalledWith(2, { roles: ['non_spending'] }));
  });

  test('merging folds one category into another', async () => {
    const user = await openPane();
    mergeCategory.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    await user.selectOptions(screen.getByLabelText('Merge into'), '3');

    await waitFor(() => expect(mergeCategory).toHaveBeenCalledWith(2, 3));
  });

  test('archiving is offered as the non-destructive option', async () => {
    const user = await openPane();
    patchCategory.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    await waitFor(() => expect(patchCategory).toHaveBeenCalledWith(2, { archived: true }));
  });

  test('deleting asks first, because no undo puts the labels back', async () => {
    const user = await openPane();
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(false);
    await expand(user, 'Groceries');

    await user.click(screen.getByRole('button', { name: 'Delete' }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(deleteCategoryById).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  test('adding a category creates it', async () => {
    const user = await openPane();
    createCategory.mockResolvedValue({ data: {} });

    await user.type(screen.getByLabelText('New category name'), 'Pets');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(createCategory).toHaveBeenCalledWith('Pets'));
  });
});

describe('grouping', () => {
  const GROUPED = [
    { id: 1, name: 'Food', color: null, roles: [], archived: false, sort: 0, parent_id: null },
    { id: 2, name: 'Groceries', color: null, roles: [], archived: false, sort: 1, parent_id: 1 },
    { id: 3, name: 'Gas', color: null, roles: [], archived: false, sort: 2, parent_id: null },
  ];

  const open = () => openPane({ rows: GROUPED, rules: [] });

  test('shows which parent a category rolls into, and how many it holds', async () => {
    await open();
    expect(screen.getByText('↳ Food')).toBeInTheDocument();
    expect(screen.getByText('group of 1')).toBeInTheDocument();
  });

  test('grouping one category under another calls the endpoint', async () => {
    const user = await open();
    setCategoryParent.mockResolvedValue({ data: {} });
    await expand(user, 'Gas');

    await user.selectOptions(screen.getByLabelText('Grouped under'), '1');

    await waitFor(() => expect(setCategoryParent).toHaveBeenCalledWith(3, 1));
  });

  test('ungrouping passes a null parent', async () => {
    const user = await open();
    setCategoryParent.mockResolvedValue({ data: {} });
    await expand(user, 'Groceries');

    await user.selectOptions(screen.getByLabelText('Grouped under'), '');

    await waitFor(() => expect(setCategoryParent).toHaveBeenCalledWith(2, null));
  });

  test('a category that already holds others cannot be nested', async () => {
    // Grouping is one level deep, so the picker refuses rather than letting
    // the server 422 after the click.
    const user = await open();
    await expand(user, 'Food');
    expect(screen.getByLabelText('Grouped under')).toBeDisabled();
  });

  test('a grouped category is not offered as a parent', async () => {
    const user = await open();
    await expand(user, 'Gas');
    const options = Array.from(screen.getByLabelText('Grouped under').options)
      .map((o) => o.textContent);
    expect(options).toContain('Food');
    expect(options).not.toContain('Groceries');
  });
});
