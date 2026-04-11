import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import SyncModal from '../SyncModal';

jest.mock('../styles', () => ({
  modal: {}, modalHeader: {}, modalTitle: {}, modalSub: {}, closeBtn: {},
  modalBody: {}, modalFooter: {}, row2: {}, fieldGroup: {}, label: {},
  input: {}, btn: {}, btnSecondary: {}, btnTeller: {}, btnPrimary: {},
}));

jest.mock('../Backdrop', () => ({ onClose, children, zIndex }) => (
  <div data-testid="backdrop">{children}</div>
));

function renderModal(handlers = {}) {
  return render(
    <SyncModal
      onSync={jest.fn()}
      onClose={jest.fn()}
      {...handlers}
    />
  );
}

test('renders modal title', () => {
  renderModal();
  expect(screen.getByText(/Sync Bank Transactions/)).toBeInTheDocument();
});

test('renders date inputs', () => {
  renderModal();
  const dateInputs = screen.getAllByDisplayValue(/-/); // YYYY-MM-DD pattern
  expect(dateInputs.length).toBeGreaterThanOrEqual(2);
});

test('renders preset buttons', () => {
  renderModal();
  expect(screen.getByText('Previous month')).toBeInTheDocument();
  expect(screen.getByText('This month')).toBeInTheDocument();
  expect(screen.getByText('Custom range')).toBeInTheDocument();
});

test('Cancel button calls onClose', () => {
  const mockClose = jest.fn();
  renderModal({ onClose: mockClose });
  fireEvent.click(screen.getByText('Cancel'));
  expect(mockClose).toHaveBeenCalled();
});

test('close (✕) button calls onClose', () => {
  const mockClose = jest.fn();
  renderModal({ onClose: mockClose });
  fireEvent.click(screen.getByText('✕'));
  expect(mockClose).toHaveBeenCalled();
});

test('Sync button calls onSync with from/to dates', () => {
  const mockSync = jest.fn();
  renderModal({ onSync: mockSync });
  // The sync button text includes the date range
  const syncBtn = screen.getByRole('button', { name: /Sync/ });
  expect(syncBtn).not.toBeDisabled();
  fireEvent.click(syncBtn);
  expect(mockSync).toHaveBeenCalledWith(
    expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)
  );
});

test('Previous month preset button fills in date range', () => {
  const { container } = renderModal();
  fireEvent.click(screen.getByText('Previous month'));
  const dateInputs = within(container).getAllByDisplayValue(/-/);
  // Both inputs should have valid YYYY-MM-DD values
  expect(dateInputs[0].value).toMatch(/^\d{4}-\d{2}-01$/); // first day of month
  expect(dateInputs[1].value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});
