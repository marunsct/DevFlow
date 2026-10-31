import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelPinSwitch } from './ModelPinSwitch';
import { FeedbackProvider } from './Feedback';

const known = vi.hoisted(() => ({ setModelPin: vi.fn() }));
vi.mock('../api', () => known);

const show = (props: Partial<React.ComponentProps<typeof ModelPinSwitch>> = {}) =>
  render(
    <FeedbackProvider>
      <ModelPinSwitch runId="run-1" pinned={false} model="model-a" endpoint="127.0.0.1:8888" {...props} />
    </FeedbackProvider>,
  );

describe('the model pin switch', () => {
  beforeEach(() => {
    known.setModelPin.mockReset();
    known.setModelPin.mockResolvedValue({ model_pinned: true, model_last: null });
  });

  it('is a switch that says whether the run follows the settings or is kept on its model', () => {
    show();
    const toggle = screen.getByRole('switch', { name: 'Keep this run on its model' });
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText('Follows the settings')).toBeTruthy();
    expect(screen.getByText('(model-a @ 127.0.0.1:8888)')).toBeTruthy();
  });

  it('moves at once, sends the choice for its own run and reports the new state', async () => {
    const changed = vi.fn();
    show({ onChanged: changed });

    await userEvent.click(screen.getByRole('switch'));

    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByText('Kept on its model')).toBeTruthy();
    await waitFor(() => expect(known.setModelPin).toHaveBeenCalledWith('run-1', true));
    await waitFor(() => expect(changed).toHaveBeenCalledWith(true));
  });

  it('turns a pinned run back to following the settings', async () => {
    show({ pinned: true });
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');

    await userEvent.click(screen.getByRole('switch'));

    await waitFor(() => expect(known.setModelPin).toHaveBeenCalledWith('run-1', false));
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('goes back and says why when the server refuses', async () => {
    known.setModelPin.mockRejectedValue({ response: { data: { detail: 'no such run' } } });
    show();

    await userEvent.click(screen.getByRole('switch'));

    await waitFor(() => expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false'));
  });

  it('shrinks to the state in a table row and keeps the model in the tooltip', () => {
    show({ compact: true, pinned: true });
    expect(screen.getByText('Pinned')).toBeTruthy();
    expect(screen.queryByText('(model-a @ 127.0.0.1:8888)')).toBeNull();
    expect(screen.getByRole('switch').getAttribute('title')).toContain('model-a @ 127.0.0.1:8888');
  });
});
