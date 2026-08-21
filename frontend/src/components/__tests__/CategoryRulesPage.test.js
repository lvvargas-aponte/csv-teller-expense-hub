import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import CategoryRulesPage from '../transactions/CategoryRulesPage';
import * as api from '../../api/categoryRules';

jest.mock('../../api/categoryRules');
jest.mock('../../hooks/useCategories', () => ({
  useCategories: () => ({ categories: ['Rent', 'Groceries'], addLocal: jest.fn() }),
}));

const RENT_RULE = {
  id: 'rule_1',
  match: 'description_contains',
  value: 'Zelle payment to Luz Valeria',
  category: 'Rent',
  amount: 1305.93,
  transaction_type: 'debit',
  enabled: true,
  notes: '',
};

beforeEach(() => {
  jest.clearAllMocks();
  api.listCategoryRules.mockResolvedValue({ data: [RENT_RULE] });
  api.createCategoryRule.mockResolvedValue({ data: RENT_RULE });
  api.updateCategoryRule.mockResolvedValue({ data: RENT_RULE });
  api.deleteCategoryRule.mockResolvedValue({ data: null });
});

// The form's <select> options carry the same labels as the table cells
// ("Money out", "Either"), so row assertions are scoped to the table.
const rulesTable = () => within(screen.getByRole('table'));

test('lists existing rules with amount, direction and category', async () => {
  render(<CategoryRulesPage />);
  expect(await screen.findByText(/Zelle payment to Luz Valeria/)).toBeInTheDocument();
  expect(rulesTable().getByText('$1,305.93')).toBeInTheDocument();
  expect(rulesTable().getByText('Money out')).toBeInTheDocument();
  expect(rulesTable().getByText('Rent')).toBeInTheDocument();
});

test('shows Any / Either for an unconstrained rule', async () => {
  api.listCategoryRules.mockResolvedValue({
    data: [{ ...RENT_RULE, amount: null, transaction_type: null }],
  });
  render(<CategoryRulesPage />);
  await screen.findByText(/Zelle payment to Luz Valeria/);
  expect(rulesTable().getByText('Any')).toBeInTheDocument();
  expect(rulesTable().getByText('Either')).toBeInTheDocument();
});

test('creating a rule sends a blank amount as null rather than 0', async () => {
  api.listCategoryRules.mockResolvedValue({ data: [] });
  render(<CategoryRulesPage />);
  await screen.findByText(/No rules yet/);

  fireEvent.change(screen.getByPlaceholderText(/Luz Valeria/), {
    target: { value: 'STARBUCKS' },
  });
  fireEvent.change(screen.getByPlaceholderText('Select or type…'), {
    target: { value: 'Coffee' },
  });
  fireEvent.click(screen.getByRole('button', { name: /Add rule/ }));

  await waitFor(() => expect(api.createCategoryRule).toHaveBeenCalled());
  expect(api.createCategoryRule).toHaveBeenCalledWith(
    expect.objectContaining({ value: 'STARBUCKS', category: 'Coffee', amount: null })
  );
});

test('a rule with no category is rejected before hitting the API', async () => {
  api.listCategoryRules.mockResolvedValue({ data: [] });
  render(<CategoryRulesPage />);
  await screen.findByText(/No rules yet/);

  fireEvent.change(screen.getByPlaceholderText(/Luz Valeria/), {
    target: { value: 'STARBUCKS' },
  });
  fireEvent.click(screen.getByRole('button', { name: /Add rule/ }));

  expect(await screen.findByText(/needs both something to match on and a category/i))
    .toBeInTheDocument();
  expect(api.createCategoryRule).not.toHaveBeenCalled();
});

test('preview shows pending changes and writes nothing until confirmed', async () => {
  api.applyCategoryRules.mockResolvedValue({
    data: {
      scanned: 310,
      matched: 3,
      changed: 2,
      truncated: false,
      changes: [
        {
          transaction_id: 't1', date: '2026-07-30',
          description: 'Zelle payment to Luz Valeria Vargas-Aponte',
          amount: 1305.93, from_category: null, to_category: 'Rent',
        },
        {
          transaction_id: 't2', date: '2026-05-31',
          description: 'Zelle payment to Luz Valeria Vargas-Aponte',
          amount: 1305.93, from_category: null, to_category: 'Rent',
        },
      ],
    },
  });

  render(<CategoryRulesPage />);
  await screen.findByText(/Zelle payment to Luz Valeria/);

  fireEvent.click(screen.getByRole('button', { name: 'Apply to existing transactions' }));

  expect(await screen.findByText(/2 transactions would change/)).toBeInTheDocument();
  expect(api.applyCategoryRules).toHaveBeenCalledWith(
    expect.objectContaining({ mode: 'preview', overwrite: false })
  );
  expect(api.applyCategoryRules).not.toHaveBeenCalledWith(
    expect.objectContaining({ mode: 'apply' })
  );

  fireEvent.click(screen.getByRole('button', { name: /Apply to 2/ }));
  await waitFor(() => expect(api.applyCategoryRules).toHaveBeenCalledWith(
    expect.objectContaining({ mode: 'apply', overwrite: false })
  ));
  expect(await screen.findByText(/Categorized 2 transactions/)).toBeInTheDocument();
});

test('the replacing variant previews with overwrite set', async () => {
  api.applyCategoryRules.mockResolvedValue({
    data: { scanned: 10, matched: 1, changed: 1, truncated: false, changes: [] },
  });
  render(<CategoryRulesPage />);
  await screen.findByText(/Zelle payment to Luz Valeria/);

  fireEvent.click(screen.getByRole('button', { name: /replacing existing categories/ }));

  await waitFor(() => expect(api.applyCategoryRules).toHaveBeenCalledWith(
    expect.objectContaining({ mode: 'preview', overwrite: true })
  ));
});

test('toggling Active flips enabled without changing the rest of the rule', async () => {
  render(<CategoryRulesPage />);
  await screen.findByText(/Zelle payment to Luz Valeria/);

  fireEvent.click(screen.getByRole('checkbox', { name: /Disable this rule/ }));

  await waitFor(() => expect(api.updateCategoryRule).toHaveBeenCalledWith(
    'rule_1',
    expect.objectContaining({ enabled: false, category: 'Rent', amount: 1305.93 })
  ));
});
