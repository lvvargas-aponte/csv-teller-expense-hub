import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import EditModal from '../transactions/EditModal';

// Prevent styles.js DOM injection and Backdrop portal complications
jest.mock('../ui/styles', () => ({
  modal: {}, modalHeader: {}, modalTitle: {}, modalSub: {}, closeBtn: {},
  modalBody: {}, modalFooter: {}, toggleRow: {}, segmented: {}, seg: {},
  segActive: {}, row2: {}, splitRow: {}, splitBtn: {}, fieldGroup: {},
  label: {}, input: {}, btn: {}, btnSecondary: {}, btnPrimary: {},
}));

jest.mock('../ui/Backdrop', () => ({ onClose, children }) => (
  <div data-testid="backdrop">{children}</div>
));

const baseTxn = {
  id: 'txn_1',
  date: '2024-01-15',
  description: 'STARBUCKS',
  amount: -9.00,
  is_shared: false,
  who: '',
  what: '',
  person_1_owes: 0,
  person_2_owes: 0,
  notes: '',
};

const personNames = { person_1: 'Alice', person_2: 'Bob' };

function renderModal(txnOverrides = {}, handlers = {}) {
  return render(
    <EditModal
      txn={{ ...baseTxn, ...txnOverrides }}
      personNames={personNames}
      onSave={jest.fn()}
      onClose={jest.fn()}
      {...handlers}
    />
  );
}

test('renders transaction description in header', () => {
  renderModal();
  expect(screen.getByText('STARBUCKS')).toBeInTheDocument();
});

test('renders formatted date and amount in subtitle', () => {
  renderModal();
  expect(screen.getByText(/Jan/)).toBeInTheDocument();
  expect(screen.getByText(/\$9\.00/)).toBeInTheDocument();
});

test('Cancel button calls onClose', () => {
  const mockClose = jest.fn();
  renderModal({}, { onClose: mockClose });
  fireEvent.click(screen.getByText('Cancel'));
  expect(mockClose).toHaveBeenCalled();
});

test('close (✕) button calls onClose', () => {
  const mockClose = jest.fn();
  renderModal({}, { onClose: mockClose });
  fireEvent.click(screen.getByText('✕'));
  expect(mockClose).toHaveBeenCalled();
});

test('split fields are hidden when Personal is selected', () => {
  renderModal({ is_shared: false });
  expect(screen.queryByText('Who paid?')).not.toBeInTheDocument();
});

test('clicking Shared reveals split fields', () => {
  renderModal({ is_shared: false });
  fireEvent.click(screen.getByText('Shared'));
  expect(screen.getByText('Who paid?')).toBeInTheDocument();
  expect(screen.getByText('50/50')).toBeInTheDocument();
});

test('50/50 button splits amount equally between both people', () => {
  renderModal({ is_shared: true, amount: -9.00 });
  fireEvent.click(screen.getByText('50/50'));
  // Both inputs should show 4.5
  const numberInputs = screen.getAllByRole('spinbutton');
  expect(numberInputs[0]).toHaveValue(4.5);
  expect(numberInputs[1]).toHaveValue(4.5);
});

test('Save button calls onSave with current form state', () => {
  const mockSave = jest.fn();
  renderModal({ is_shared: false }, { onSave: mockSave });
  fireEvent.click(screen.getByText('Save'));
  expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ is_shared: false }));
});

test('Save passes updated shared state when toggled to Shared', () => {
  const mockSave = jest.fn();
  renderModal({ is_shared: false }, { onSave: mockSave });
  fireEvent.click(screen.getByText('Shared'));
  fireEvent.click(screen.getByText('Save'));
  expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ is_shared: true }));
});

test('person names from props appear as labels', () => {
  renderModal({ is_shared: true });
  expect(screen.getByText(/Alice/)).toBeInTheDocument();
  expect(screen.getByText(/Bob/)).toBeInTheDocument();
});

test('notes textarea is visible when shared', () => {
  renderModal({ is_shared: true });
  expect(screen.getByPlaceholderText(/Optional notes/)).toBeInTheDocument();
});

test('does not render the legacy ✨ Suggest button (moved to bulk flow)', () => {
  renderModal();
  expect(screen.queryByRole('button', { name: /suggest/i })).not.toBeInTheDocument();
});
