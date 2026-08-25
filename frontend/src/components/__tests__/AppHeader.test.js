import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AppHeader from '../AppHeader';

function renderHeader() {
  return render(
    <MemoryRouter>
      <AppHeader isDark={false} onToggleTheme={() => {}} />
    </MemoryRouter>,
  );
}

test('the wordmark reads Fin', () => {
  renderHeader();
  expect(screen.getByRole('link', { name: /^Fin$/ })).toBeInTheDocument();
});

test('the old name is gone', () => {
  const { container } = renderHeader();
  expect(container.textContent).not.toMatch(/ExpensesHub/i);
});
