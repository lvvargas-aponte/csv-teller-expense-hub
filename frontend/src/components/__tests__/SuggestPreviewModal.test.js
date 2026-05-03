import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import SuggestPreviewModal from '../transactions/SuggestPreviewModal';

jest.mock('../ui/Backdrop', () => ({ onClose, children }) => (
  <div data-testid="backdrop">{children}</div>
));

const baseResult = {
  ai_available: true,
  candidates:   ['Groceries', 'Gas', 'Subscriptions'],
  results: [
    { id: 't1', description: 'WHOLE FOODS', amount: -52.30, suggested_category: 'Groceries' },
    { id: 't2', description: 'SHELL GAS',   amount: -40.00, suggested_category: 'Gas' },
    { id: 't3', description: 'MYSTERY CO',  amount: -10.00, suggested_category: null },
  ],
  skipped_ids: ['t4'],
  not_found:   [],
};

function renderModal(overrides = {}, handlers = {}) {
  return render(
    <SuggestPreviewModal
      result={{ ...baseResult, ...overrides }}
      onApply={jest.fn()}
      onClose={jest.fn()}
      {...handlers}
    />
  );
}

test('renders one row per result with prefilled suggested category', () => {
  renderModal();
  expect(screen.getByText('WHOLE FOODS')).toBeInTheDocument();
  expect(screen.getByText('SHELL GAS')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Groceries')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Gas')).toBeInTheDocument();
});

test('shows skipped count in subtitle', () => {
  renderModal();
  expect(screen.getByText(/1 already categorized/i)).toBeInTheDocument();
});

test('Apply payload only includes checked rows with non-empty category', () => {
  const onApply = jest.fn();
  renderModal({}, { onApply });

  // t3 starts unchecked (no suggestion); leave it that way.
  // Uncheck t2 by clicking its checkbox.
  const t2Checkbox = screen.getByLabelText('Include SHELL GAS');
  fireEvent.click(t2Checkbox);

  fireEvent.click(screen.getByRole('button', { name: /apply/i }));

  expect(onApply).toHaveBeenCalledWith([
    { transaction_id: 't1', category: 'Groceries' },
  ]);
});

test('editing a category overrides the suggestion in the apply payload', () => {
  const onApply = jest.fn();
  renderModal({}, { onApply });

  const grocInput = screen.getByDisplayValue('Groceries');
  fireEvent.change(grocInput, { target: { value: 'Dining' } });

  // Uncheck t2 to keep payload focused
  fireEvent.click(screen.getByLabelText('Include SHELL GAS'));

  fireEvent.click(screen.getByRole('button', { name: /apply/i }));
  expect(onApply).toHaveBeenCalledWith([
    { transaction_id: 't1', category: 'Dining' },
  ]);
});

test('shows Ollama-down banner and disables Apply when ai_available=false', () => {
  renderModal({
    ai_available: false,
    results: [
      { id: 't1', description: 'WHOLE FOODS', amount: -52.30, suggested_category: null },
    ],
  });
  expect(screen.getByText(/Ollama is not running/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled();
});

test('Cancel calls onClose', () => {
  const onClose = jest.fn();
  renderModal({}, { onClose });
  fireEvent.click(screen.getByText('Cancel'));
  expect(onClose).toHaveBeenCalled();
});
