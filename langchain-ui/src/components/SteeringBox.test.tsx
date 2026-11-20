import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SteeringBox } from './SteeringBox';
import { FeedbackProvider } from './Feedback';

const known = vi.hoisted(() => ({
  getSteering: vi.fn(),
  sendSteering: vi.fn(),
  editSteering: vi.fn(),
  withdrawSteering: vi.fn(),
  pauseRun: vi.fn(),
  resumeWithDirection: vi.fn(),
}));
vi.mock('../api', () => known);

const queued = { id: 'N-1', text: 'keep the store in one file', by: 'owner', at: '2026-11-20T00:00:00Z', scope: 'run', state: 'queued' };
const read = { id: 'N-2', text: 'use the existing sign-in page', by: 'owner', at: '2026-11-20T00:01:00Z', scope: 'next_stage',
  state: 'read', applied_stage: 'defect_fix_2_3', applied_at: '2026-11-20T00:02:00Z' };
const withdrawn = { id: 'N-3', text: 'drop the export', by: 'owner', at: '2026-11-20T00:03:00Z', scope: 'run', state: 'withdrawn' };

const show = (props: Partial<React.ComponentProps<typeof SteeringBox>> = {}) =>
  render(
    <FeedbackProvider>
      <SteeringBox runId="run-1" stage="defect_fix_2_3" status="running" {...props} />
    </FeedbackProvider>,
  );

const openIt = async () => userEvent.click(await screen.findByText('Steer this run…'));
const itemOf = (text: string) => screen.getByText(text).closest('li') as HTMLElement;

describe('the steering box', () => {
  beforeEach(() => {
    for (const fn of Object.values(known)) fn.mockReset();
    known.getSteering.mockResolvedValue([queued, read, withdrawn]);
    known.pauseRun.mockResolvedValue({ message: 'pausing' });
    known.resumeWithDirection.mockResolvedValue({ message: 'resumed' });
  });

  it('shows a waiting note greyed, a read one with the stage that read it, and a withdrawn one struck through', async () => {
    show();
    await openIt();
    await screen.findByText('keep the store in one file');

    expect(itemOf('keep the store in one file').getAttribute('data-state')).toBe('queued');
    expect(itemOf('keep the store in one file').className).toContain('opacity-70');
    expect(within(itemOf('keep the store in one file')).getByText(/Waiting/)).toBeTruthy();
    expect(within(itemOf('use the existing sign-in page')).getByText(/^Read by /)).toBeTruthy();
    expect(screen.getByText('drop the export').className).toContain('line-through');
    // Only the waiting note can be changed.
    expect(within(itemOf('use the existing sign-in page')).queryByText('Edit')).toBeNull();
    expect(within(itemOf('drop the export')).queryByText('Withdraw')).toBeNull();
  });

  it('edits and withdraws a waiting note', async () => {
    known.editSteering.mockResolvedValue({ ...queued, text: 'keep the store in two files', edited_at: '2026-11-20T00:05:00Z' });
    known.withdrawSteering.mockResolvedValue({ ...queued, text: 'keep the store in two files', state: 'withdrawn' });
    show();
    await openIt();
    await screen.findByText('keep the store in one file');

    await userEvent.click(within(itemOf('keep the store in one file')).getByText('Edit'));
    const box = screen.getByLabelText('New words for this note');
    await userEvent.clear(box);
    await userEvent.type(box, 'keep the store in two files');
    await userEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(known.editSteering).toHaveBeenCalledWith('run-1', 'N-1', 'keep the store in two files'));

    await userEvent.click(within(itemOf('keep the store in two files')).getByText('Withdraw'));
    await waitFor(() => expect(known.withdrawSteering).toHaveBeenCalledWith('run-1', 'N-1'));
    await waitFor(() => expect(screen.getByText('keep the store in two files').className).toContain('line-through'));
  });

  it('says why a note already read cannot be edited', async () => {
    known.editSteering.mockRejectedValue({ response: { data: { detail: 'Note N-1 was already read by defect_fix_2_3, so it cannot be changed' } } });
    show();
    await openIt();
    await screen.findByText('keep the store in one file');

    await userEvent.click(within(itemOf('keep the store in one file')).getByText('Edit'));
    await userEvent.click(screen.getByText('Save'));

    expect(await screen.findByText(/already read by defect_fix_2_3/)).toBeTruthy();
  });

  it('offers three levels and sends "This agent" as a note for the stage working now', async () => {
    known.sendSteering.mockResolvedValue({ ...queued, id: 'N-4', text: 'name the table notes', scope: 'next_stage' });
    show();
    await openIt();

    for (const name of ['This agent', 'The whole run', 'Stop and redirect']) expect(screen.getByLabelText(name)).toBeTruthy();
    await userEvent.click(screen.getByLabelText('This agent'));
    await userEvent.type(screen.getByLabelText('Direction for this run'), 'name the table notes');
    await userEvent.click(screen.getByText('Send'));

    await waitFor(() => expect(known.sendSteering).toHaveBeenCalledWith('run-1', 'name the table notes', 'next_stage', ['all']));
  });

  it('stops at the end of the stage, then resumes with the direction once the run has paused', async () => {
    const shown = show();
    await openIt();

    await userEvent.click(screen.getByLabelText('Stop and redirect'));
    await userEvent.type(screen.getByLabelText('Direction for this run'), 'start the page again from the brief');
    await userEvent.click(screen.getByRole('button', { name: 'Stop and redirect' }));

    await waitFor(() => expect(known.pauseRun).toHaveBeenCalledWith('run-1', true));
    expect((await screen.findByTestId('redirect-pending')).textContent).toContain('start the page again from the brief');
    expect(known.resumeWithDirection).not.toHaveBeenCalled();

    shown.rerender(
      <FeedbackProvider>
        <SteeringBox runId="run-1" stage="defect_fix_2_3" status="paused" />
      </FeedbackProvider>,
    );
    await waitFor(() => expect(known.resumeWithDirection).toHaveBeenCalledWith('run-1', 'start the page again from the brief'));
  });

  it('keeps a note for a paused run and says it waits for the resume', async () => {
    known.getSteering.mockResolvedValue([]);
    known.sendSteering.mockResolvedValue({ ...queued, id: 'N-1' });
    show({ status: 'paused' });
    await openIt();

    expect(screen.getByText('The run is paused. A note waits and is read when it resumes.')).toBeTruthy();
    await userEvent.type(screen.getByLabelText('Direction for this run'), 'keep the store in one file');
    await userEvent.click(screen.getByText('Send'));

    await waitFor(() => expect(known.sendSteering).toHaveBeenCalledWith('run-1', 'keep the store in one file', 'run', ['all']));
  });

  it('says on each note who it is for and who read it', async () => {
    known.getSteering.mockResolvedValue([{ ...queued, audience: ['build'] }, { ...read, audience: ['all'] }, withdrawn]);
    show();
    await openIt();
    await screen.findByText('keep the store in one file');

    expect(within(itemOf('keep the store in one file')).getByText(/for the builders/)).toBeTruthy();
    const readNote = within(itemOf('use the existing sign-in page'));
    expect(readNote.getByText(/^Read by /)).toBeTruthy();
    expect(readNote.getByText(/for everyone/)).toBeTruthy();
    // A note kept before audiences existed is for everyone.
    expect(within(itemOf('drop the export')).getByText(/for everyone/)).toBeTruthy();
  });

  it('sends a note for the whole run to the audience chosen', async () => {
    known.sendSteering.mockResolvedValue({ ...queued, id: 'N-4', text: 'keep the tables small', audience: ['database'] });
    show();
    await openIt();

    await userEvent.selectOptions(screen.getByLabelText('Who it is for'), 'database');
    await userEvent.type(screen.getByLabelText('Direction for this run'), 'keep the tables small');
    await userEvent.click(screen.getByText('Send'));

    await waitFor(() => expect(known.sendSteering).toHaveBeenCalledWith('run-1', 'keep the tables small', 'run', ['database']));
    expect(within(await waitFor(() => itemOf('keep the tables small'))).getByText(/for the database builder/)).toBeTruthy();
  });

  it('reads the notes again when the run says one was read', async () => {
    const shown = show({ heard: 0 });
    await waitFor(() => expect(known.getSteering).toHaveBeenCalledTimes(1));

    shown.rerender(
      <FeedbackProvider>
        <SteeringBox runId="run-1" stage="defect_fix_2_3" status="running" heard={1} />
      </FeedbackProvider>,
    );

    await waitFor(() => expect(known.getSteering).toHaveBeenCalledTimes(2));
  });
});
