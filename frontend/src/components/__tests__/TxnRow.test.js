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

function renderRow(overrides = {}, handlers = {}) {
  return render(
    <table><tbody>
      <TxnRow
        txn={{ ...baseTxn, ...overrides }}
        otherPersonName="Bob"
        isSelected={false}
        onToggle={jest.fn()}
        onQuickMark={jest.fn().mockResolvedValue()}
        onEdit={jest.fn()}
        onNote={jest.fn()}
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

test('shows other person owed amount when shared', () => {
  renderRow({ is_shared: true, person_2_owes: 2.25 });
  // TxnRow shows only the other person (otherPersonName) and their owed amount
  expect(screen.getByText(/Bob/)).toBeInTheDocument();
  expect(screen.getByText(/\$2\.25/)).toBeInTheDocument();
});

test('shows formatted category when category is set', () => {
  renderRow({ category: 'food_and_drink' });
  // formatCategory converts underscores to spaces and title-cases each word
  expect(screen.getByText('Food And Drink')).toBeInTheDocument();
});

test('shows 📝 note icon when notes are present', () => {
  renderRow({ notes: 'Split with roommate' });
  // When notes exist the icon changes from 🗒️ to 📝
  expect(screen.getByTitle('Split with roommate')).toBeInTheDocument();
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

test('calls onEdit when the adjust-split button is clicked', () => {
  const mockEdit = jest.fn();
  renderRow({}, { onEdit: mockEdit });
  fireEvent.click(screen.getByTitle('Adjust split'));
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
  renderRow({}, { isSelected: true });
  expect(screen.getByRole('checkbox')).toBeChecked();
});
