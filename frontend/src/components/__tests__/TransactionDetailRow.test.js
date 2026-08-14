import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TransactionDetailRow from '../transactions/TransactionDetailRow';

const baseTxn = {
  id: 'test_1',
  date: '2024-01-15',
  description: 'STARBUCKS',
  amount: -9.0,
  source: 'discover',
  institution: 'Discover',
  account_type: 'credit_card',
  account_id: 'acct_9',
  is_shared: false,
  who: '',
  what: '',
  person_1_owes: 0,
  person_2_owes: 0,
  notes: '',
  reviewed: false,
  transaction_type: 'debit',
};

const personNames = { person_1: 'Alice', person_2: 'Bob' };

function buildRow(overrides = {}, handlers = {}) {
  return (
    <table><tbody>
      <TransactionDetailRow
        txn={{ ...baseTxn, ...overrides }}
        colSpan={8}
        personNames={personNames}
        categories={['Food', 'Travel']}
        onSave={jest.fn().mockResolvedValue()}
        onDelete={jest.fn()}
        onClose={jest.fn()}
        {...handlers}
      />
    </tbody></table>
  );
}

function renderRow(overrides = {}, handlers = {}) {
  return render(buildRow(overrides, handlers));
}

test('renders the amount and date/institution subtitle', () => {
  renderRow();
  expect(screen.getByText('$9.00')).toBeInTheDocument();
  expect(screen.getByText(/Jan 15, 2024 · Discover Credit Card/)).toBeInTheDocument();
});

test('Collapse calls onClose', () => {
  const onClose = jest.fn();
  renderRow({}, { onClose });
  fireEvent.click(screen.getByRole('button', { name: 'Collapse' }));
  expect(onClose).toHaveBeenCalled();
});

test('Delete calls onDelete with the transaction', () => {
  const onDelete = jest.fn();
  renderRow({}, { onDelete });
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
  expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 'test_1' }));
});

test('shared fields are hidden when the split is personal', () => {
  renderRow({ is_shared: false });
  expect(screen.queryByLabelText('Who paid?')).not.toBeInTheDocument();
  expect(screen.queryByText('50/50')).not.toBeInTheDocument();
});

test('clicking Shared reveals the who/what/owed fields', () => {
  renderRow({ is_shared: false });
  fireEvent.click(screen.getByRole('button', { name: 'Shared' }));
  expect(screen.getByLabelText('Who paid?')).toBeInTheDocument();
  expect(screen.getByLabelText('What for?')).toBeInTheDocument();
  expect(screen.getByLabelText('Alice owes')).toBeInTheDocument();
  expect(screen.getByLabelText('Bob owes')).toBeInTheDocument();
});

test('50/50 fills both owed fields with half the amount', () => {
  renderRow({ is_shared: true });
  fireEvent.click(screen.getByRole('button', { name: '50/50' }));
  expect(screen.getByLabelText('Alice owes')).toHaveValue(4.5);
  expect(screen.getByLabelText('Bob owes')).toHaveValue(4.5);
});

test('notes textarea is always visible', () => {
  renderRow();
  expect(screen.getByLabelText('Notes')).toBeInTheDocument();
});

test('Save is disabled until the form is dirty, then shows the dirty marker and Cancel', () => {
  renderRow();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'hello' } });
  expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
});

test('Cancel restores the pristine values and hides itself', () => {
  renderRow({ notes: 'original' });
  const notes = screen.getByLabelText('Notes');
  fireEvent.change(notes, { target: { value: 'edited' } });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('Notes')).toHaveValue('original');
  expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
});

test('Save sends the full form when shared', async () => {
  const onSave = jest.fn().mockResolvedValue();
  renderRow({ is_shared: true, who: 'Alice', what: 'Coffee' }, { onSave });
  fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'note' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'test_1' }),
    expect.objectContaining({
      is_shared: true, who: 'Alice', what: 'Coffee', notes: 'note',
    })
  ));
});

test('Save blanks the shared fields when the split is personal', async () => {
  const onSave = jest.fn().mockResolvedValue();
  renderRow({ is_shared: true, who: 'Alice', person_1_owes: 4.5, person_2_owes: 4.5 }, { onSave });
  fireEvent.click(screen.getByRole('button', { name: 'Personal' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'test_1' }),
    expect.objectContaining({
      is_shared: false, who: '', what: '', person_1_owes: 0, person_2_owes: 0,
    })
  ));
});

test('the Reviewed switch toggles aria-checked and dirties the form', () => {
  renderRow({ reviewed: false });
  const sw = screen.getByRole('switch', { name: 'Reviewed' });
  expect(sw).toHaveAttribute('aria-checked', 'false');
  fireEvent.click(sw);
  expect(sw).toHaveAttribute('aria-checked', 'true');
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
});

test('onDraftChange reports pending category and split', () => {
  const onDraftChange = jest.fn();
  renderRow({ is_shared: false }, { onDraftChange });
  fireEvent.click(screen.getByRole('button', { name: 'Shared' }));
  expect(onDraftChange).toHaveBeenLastCalledWith({ category: '', is_shared: true });
});

test('renders source-record metadata and omits empty rows', () => {
  renderRow({ direction: 'outflow' });
  expect(screen.getByText('Institution')).toBeInTheDocument();
  expect(screen.getByText('Discover')).toBeInTheDocument();
  expect(screen.getByText('Direction')).toBeInTheDocument();
  expect(screen.getByText('outflow')).toBeInTheDocument();
  expect(screen.getByText('acct_9')).toBeInTheDocument();
  // No post_date / transfer_to_account_id on the base txn → rows omitted.
  expect(screen.queryByText('Posted')).not.toBeInTheDocument();
  expect(screen.queryByText('Transfer to')).not.toBeInTheDocument();
});

test('switching to a different transaction discards the draft', () => {
  const { rerender } = renderRow();
  fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'draft text' } });
  rerender(buildRow({ id: 'test_2', notes: 'other' }));
  expect(screen.getByLabelText('Notes')).toHaveValue('other');
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
});
