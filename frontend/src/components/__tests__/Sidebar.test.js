import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Sidebar from '../Sidebar';
import { NAV } from '../../navConfig';
import { UnsavedChangesContext } from '../../contexts/UnsavedChangesContext';

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

test('exposes exactly one navigation landmark, distinctly labelled', () => {
  const { container } = renderAt('/');

  const navs = container.querySelectorAll('nav');
  expect(navs).toHaveLength(1);
  expect(navs[0]).toHaveAttribute('aria-label', 'Main');
});

test('the collapse control is reachable and states what it does', () => {
  // The old sidebars rendered bare chevron glyphs, one of them without
  // aria-hidden, so the control announced as a stray character.
  renderAt('/');
  const toggle = screen.getByRole('button', { name: /collapse sidebar/i });
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
});

// The in-app unsaved-settings guard: SettingsPage flags `unsaved` via
// context; Sidebar must confirm before letting a nav click through.
function renderWithRoutes(unsaved) {
  return render(
    <MemoryRouter initialEntries={['/accounts']}>
      <UnsavedChangesContext.Provider value={{ unsaved, setUnsaved: () => {} }}>
        <Sidebar healthScore={72} />
        <Routes>
          <Route path="/accounts" element={<div>Accounts page</div>} />
          <Route path="/" element={<div>Home page</div>} />
        </Routes>
      </UnsavedChangesContext.Provider>
    </MemoryRouter>,
  );
}

test('a declined confirm cancels in-app navigation away from unsaved settings', async () => {
  window.confirm = jest.fn(() => false);
  renderWithRoutes(true);

  await userEvent.click(screen.getByRole('link', { name: 'Home' }));

  expect(window.confirm).toHaveBeenCalled();
  expect(screen.getByText('Accounts page')).toBeInTheDocument();
  expect(screen.queryByText('Home page')).toBeNull();
});

test('an accepted confirm allows in-app navigation away from unsaved settings', async () => {
  window.confirm = jest.fn(() => true);
  renderWithRoutes(true);

  await userEvent.click(screen.getByRole('link', { name: 'Home' }));

  expect(window.confirm).toHaveBeenCalled();
  expect(screen.getByText('Home page')).toBeInTheDocument();
});

test('no confirm is asked when there is nothing unsaved', async () => {
  window.confirm = jest.fn(() => false);
  renderWithRoutes(false);

  await userEvent.click(screen.getByRole('link', { name: 'Home' }));

  expect(window.confirm).not.toHaveBeenCalled();
  expect(screen.getByText('Home page')).toBeInTheDocument();
});
