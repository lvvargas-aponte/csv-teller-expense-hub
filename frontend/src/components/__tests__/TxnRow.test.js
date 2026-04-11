import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TxnRow from '../TxnRow';

jest.mock('../styles', () => ({
  row: {}, rowSelected: {}, rowShared: {},
  td: {}, badge: {}, sharedBadge: {}, personalBadge: {},
  actionGroup: {}, inlineToggle: {}, toggleBtn: {},
  toggleBtnActivePersonal: {}, toggleBtnActiveShared: {}, editBtn: {},
}));

const baseTxn = {
  id: 'test_1',
  date: '2024-01-15',
  description: 'STARBUCKS',
  amount: -4.50,
  source: 'discover',
  is_shared: false,
  person_1_owes: 0,
  person_2_owes: 0,
  notes: '',
  what: '',
};

const personNames = { person_1: 'Alice', person_2: 'Bob' };

function renderRow(overrides = {}, handlers = {}) {
  return render(
    <table><tbody>
      <TxnRow
        txn={{ ...baseTxn, ...overrides }}
        personNames={personNames}
        isSelected={false}
        onToggle={jest.fn()}
        onQuickMark={jest.fn().mockResolvedValue()}
        onEdit={jest.fn()}
        {...handlers}
      />
    </tbody></table>
  );
}

test('renders description', () => {
  renderRow();
  expect(screen.getByText('STARBUCKS')).toBeInTheDocument();
});

test('renders formatted date', () => {
  renderRow();
  expect(screen.getByText(/Jan/)).toBeInTheDocument();
});

test('shows "personal" badge when not shared', () => {
  renderRow({ is_shared: false });
  expect(screen.getByText('personal')).toBeInTheDocument();
});

test('shows "shared" badge when is_shared is true', () => {
  renderRow({ is_shared: true, person_1_owes: 2.25, person_2_owes: 2.25 });
  expect(screen.getByText('shared')).toBeInTheDocument();
});

test('shows person owed amounts when shared', () => {
  renderRow({ is_shared: true, person_1_owes: 2.25, person_2_owes: 2.25 });
  expect(screen.getByText(/Alice/)).toBeInTheDocument();
  expect(screen.getByText(/Bob/)).toBeInTheDocument();
});

test('shows "what" label when shared and what is set', () => {
  renderRow({ is_shared: true, what: 'Groceries', person_1_owes: 0, person_2_owes: 0 });
  expect(screen.getByText('Groceries')).toBeInTheDocument();
});

test('shows notes when present', () => {
  renderRow({ notes: 'Split with roommate' });
  expect(screen.getByText('Split with roommate')).toBeInTheDocument();
});

test('calls onQuickMark with (txn, true) when 50/50 button clicked', async () => {
  const mockMark = jest.fn().mockResolvedValue();
  renderRow({ is_shared: false }, { onQuickMark: mockMark });
  fireEvent.click(screen.getByText('50/50'));
  await waitFor(() => expect(mockMark).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'test_1' }),
    true
  ));
});

test('calls onQuickMark with (txn, false) when Personal button clicked', async () => {
  const mockMark = jest.fn().mockResolvedValue();
  renderRow({ is_shared: true }, { onQuickMark: mockMark });
  fireEvent.click(screen.getByText('Personal'));
  await waitFor(() => expect(mockMark).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'test_1' }),
    false
  ));
});

test('calls onEdit when Edit button is clicked', () => {
  const mockEdit = jest.fn();
  renderRow({}, { onEdit: mockEdit });
  fireEvent.click(screen.getByText('Edit'));
  expect(mockEdit).toHaveBeenCalled();
});

test('calls onToggle when checkbox is clicked', () => {
  const mockToggle = jest.fn();
  renderRow({}, { onToggle: mockToggle });
  const checkbox = screen.getByRole('checkbox');
  fireEvent.click(checkbox);
  expect(mockToggle).toHaveBeenCalledWith('test_1');
});

test('checkbox is checked when isSelected is true', () => {
  render(
    <table><tbody>
      <TxnRow
        txn={baseTxn}
        personNames={personNames}
        isSelected={true}
        onToggle={jest.fn()}
        onQuickMark={jest.fn()}
        onEdit={jest.fn()}
      />
    </tbody></table>
  );
  expect(screen.getByRole('checkbox')).toBeChecked();
});
