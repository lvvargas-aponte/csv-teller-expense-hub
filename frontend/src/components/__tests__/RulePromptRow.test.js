import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RulePromptRow from '../transactions/RulePromptRow';

function renderPrompt(props = {}) {
  const onConfirm = jest.fn();
  const onDismiss = jest.fn();
  render(
    <table><tbody>
      <RulePromptRow
        colSpan={8}
        merchant="chipotle"
        category="Dining"
        claimable={23}
        protectedCount={0}
        onConfirm={onConfirm}
        onDismiss={onDismiss}
        {...props}
      />
    </tbody></table>,
  );
  return { onConfirm, onDismiss };
}

test('offers to remember the merchant, checked by default', () => {
  renderPrompt();
  const [remember] = screen.getAllByRole('checkbox');
  expect(remember).toBeChecked();
  expect(screen.getByText('chipotle')).toBeInTheDocument();
  expect(screen.getByText('Dining')).toBeInTheDocument();
});

test('the retro-apply is opt-in, and names the count', () => {
  renderPrompt();
  const [, applyExisting] = screen.getAllByRole('checkbox');
  expect(applyExisting).not.toBeChecked();
  expect(screen.getByText('Also apply to 23 past transactions')).toBeInTheDocument();
});

test('confirming reports both answers', async () => {
  const user = userEvent.setup();
  const { onConfirm } = renderPrompt();

  await user.click(screen.getAllByRole('checkbox')[1]);
  await user.click(screen.getByRole('button', { name: 'Remember' }));

  expect(onConfirm).toHaveBeenCalledWith({ remember: true, applyExisting: true });
});

test('confirming without the sweep leaves past transactions alone', async () => {
  const user = userEvent.setup();
  const { onConfirm } = renderPrompt();

  await user.click(screen.getByRole('button', { name: 'Remember' }));

  expect(onConfirm).toHaveBeenCalledWith({ remember: true, applyExisting: false });
});

test('"Not now" dismisses without creating anything', async () => {
  const user = userEvent.setup();
  const { onConfirm, onDismiss } = renderPrompt();

  await user.click(screen.getByRole('button', { name: 'Not now' }));

  expect(onDismiss).toHaveBeenCalled();
  expect(onConfirm).not.toHaveBeenCalled();
});

test('unchecking remember disables both the sweep and the confirm', async () => {
  const user = userEvent.setup();
  renderPrompt();

  await user.click(screen.getAllByRole('checkbox')[0]);

  expect(screen.getAllByRole('checkbox')[1]).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Remember' })).toBeDisabled();
});

test('hides the sweep when there is nothing to sweep', () => {
  renderPrompt({ claimable: 0 });
  expect(screen.getAllByRole('checkbox')).toHaveLength(1);
});

test('explains matches a higher source already owns', () => {
  renderPrompt({ claimable: 4, protectedCount: 2 });
  expect(
    screen.getByText(/2 other matches keep the category you or a rule already gave them/),
  ).toBeInTheDocument();
});

test('singular wording for a single past transaction', () => {
  renderPrompt({ claimable: 1 });
  expect(screen.getByText('Also apply to 1 past transaction')).toBeInTheDocument();
});
