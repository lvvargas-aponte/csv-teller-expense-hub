import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from '../Sidebar';
import { NAV } from '../../navConfig';

const renderAt = (path) => render(
  <MemoryRouter initialEntries={[path]}><Sidebar healthScore={72} /></MemoryRouter>,
);

test('renders one link per top-level destination', () => {
  renderAt('/');
  for (const section of NAV) {
    expect(screen.getByRole('link', { name: section.label })).toBeInTheDocument();
  }
});

test('marks the current section as the current page', () => {
  renderAt('/accounts');
  expect(screen.getByRole('link', { name: 'Accounts' }))
    .toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: 'Home' }))
    .not.toHaveAttribute('aria-current');
});

test('a sub-route still marks its parent section current', () => {
  renderAt('/plan/goals');
  expect(screen.getByRole('link', { name: 'Plan' }))
    .toHaveAttribute('aria-current', 'page');
});

test('Home is not marked current on every route', () => {
  // NavLink without `end` treats "/" as a prefix of everything.
  renderAt('/accounts');
  expect(screen.getByRole('link', { name: 'Home' }))
    .not.toHaveAttribute('aria-current');
});

test('shows sub-navigation for the active section', () => {
  renderAt('/transactions');
  expect(screen.getByRole('link', { name: 'Shared' })).toBeInTheDocument();
});

test('hides sub-navigation for inactive sections', () => {
  // Separate test on purpose: two renderAt calls in one test leave both
  // trees mounted, so the second query would still find the first render's
  // links and pass for the wrong reason.
  renderAt('/accounts');
  expect(screen.queryByRole('link', { name: 'Shared' })).toBeNull();
});

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

test('nav uses svg icons and carries no emoji', () => {
  const { container } = renderAt('/');
  expect(container.querySelectorAll('svg').length).toBeGreaterThanOrEqual(NAV.length);
  expect(container.textContent).not.toMatch(EMOJI);
});

test('every link has an accessible name', () => {
  renderAt('/');
  for (const link of screen.getAllByRole('link')) {
    expect(link).toHaveAccessibleName();
  }
});
