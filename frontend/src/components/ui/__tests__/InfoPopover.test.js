import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InfoPopover from '../InfoPopover';

const renderPopover = (props = {}) => render(
  <div>
    <button type="button">outside</button>
    <InfoPopover label="Net Worth" title="Net worth" {...props}>
      Assets minus liabilities across every linked account.
    </InfoPopover>
  </div>,
);

const trigger = () => screen.getByRole('button', { name: 'About Net Worth' });

test('the trigger is a button named for what it explains', () => {
  renderPopover();
  expect(trigger()).toHaveAttribute('aria-expanded', 'false');
});

test('the panel is not in the accessibility tree until it is opened', () => {
  renderPopover();
  expect(screen.queryByText(/Assets minus liabilities/)).toBeNull();
});

test('Enter opens the panel and aria-controls points at it', async () => {
  const user = userEvent.setup();
  renderPopover();
  trigger().focus();
  await user.keyboard('{Enter}');

  expect(trigger()).toHaveAttribute('aria-expanded', 'true');
  const panel = screen.getByText(/Assets minus liabilities/).closest('[id]');
  expect(trigger()).toHaveAttribute('aria-controls', panel.id);
});

test('Space opens the panel too', async () => {
  const user = userEvent.setup();
  renderPopover();
  trigger().focus();
  await user.keyboard(' ');

  expect(trigger()).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText(/Assets minus liabilities/)).toBeInTheDocument();
});

test('Escape closes the panel and returns focus to the trigger', async () => {
  const user = userEvent.setup();
  renderPopover();
  await user.click(trigger());
  expect(screen.getByText(/Assets minus liabilities/)).toBeInTheDocument();

  await user.keyboard('{Escape}');

  expect(screen.queryByText(/Assets minus liabilities/)).toBeNull();
  expect(trigger()).toHaveAttribute('aria-expanded', 'false');
  expect(trigger()).toHaveFocus();
});

test('clicking outside dismisses the panel', async () => {
  const user = userEvent.setup();
  renderPopover();
  await user.click(trigger());
  expect(screen.getByText(/Assets minus liabilities/)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'outside' }));

  expect(screen.queryByText(/Assets minus liabilities/)).toBeNull();
  expect(trigger()).toHaveAttribute('aria-expanded', 'false');
});

test('hovering is an enhancement, not the only way in', async () => {
  const user = userEvent.setup();
  renderPopover();
  await user.hover(trigger());
  expect(screen.getByText(/Assets minus liabilities/)).toBeInTheDocument();

  await user.unhover(trigger());
  expect(screen.queryByText(/Assets minus liabilities/)).toBeNull();
});
