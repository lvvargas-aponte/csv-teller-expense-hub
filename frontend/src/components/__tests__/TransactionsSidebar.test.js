import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import TransactionsSidebar from '../transactions/TransactionsSidebar';

describe('TransactionsSidebar', () => {
  test('renders a Shared nav item and navigates to it on click', () => {
    const onNavigate = jest.fn();
    render(<TransactionsSidebar activeId="current" onNavigate={onNavigate} />);

    const sharedItem = screen.getByRole('button', { name: 'Shared' });
    expect(sharedItem).toBeInTheDocument();

    fireEvent.click(sharedItem);
    expect(onNavigate).toHaveBeenCalledWith('shared');
  });
});
