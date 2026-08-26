import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AppHeader from '../AppHeader';

const renderHeader = () => render(
  <MemoryRouter><AppHeader isDark={false} onToggleTheme={() => {}} /></MemoryRouter>,
);

test('keeps the global controls', () => {
  renderHeader();
  expect(screen.getByRole('link', { name: /help/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /dark mode/i })).toBeInTheDocument();
});

test('no longer duplicates navigation the sidebar owns', () => {
  renderHeader();
  expect(screen.queryByRole('link', { name: 'Transactions' })).toBeNull();
  expect(screen.queryByRole('link', { name: 'Finances' })).toBeNull();
});

test('does not render a second wordmark', () => {
  // The sidebar owns the "Fin" wordmark. A substring check would false-fail
  // on any legitimate text containing "Fin" (e.g. "Finances"), so pin the
  // element instead.
  renderHeader();
  expect(screen.queryByText(/^Fin$/)).toBeNull();
});
