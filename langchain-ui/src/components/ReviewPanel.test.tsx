import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReviewPanel } from './ReviewPanel';
import type { ReviewPayload } from '../types';

const { fetchArtifactContent, getDocumentDiff } = vi.hoisted(() => ({
  fetchArtifactContent: vi.fn(async () => '# Specification\n\nUsers sign in with an email address.'),
  getDocumentDiff: vi.fn(async () => ({
    path: 'docs/technical_specification.md', since: 'abc1234', since_at: '2026-10-19T03:00:00Z',
    diff: '-Users sign in with a username.\n+Users sign in with an email address.', truncated: false,
  })),
}));
vi.mock('../api', () => ({ fetchArtifactContent, getDocumentDiff, downloadArtifact: vi.fn() }));

const review = (extra: Partial<ReviewPayload> = {}): ReviewPayload => ({
  point: 'technical_specification', artifact_id: 'technical-specification', revision: 2, comments: null,
  available_actions: ['approve', 'changes', 'skip'], document: 'docs/technical_specification.md', ...extra,
});

describe('a review', () => {
  it('shows its document in place, and what changed since the revision before', async () => {
    render(<ReviewPanel runId="run-1" review={review()} onSubmit={() => undefined} />);

    expect(await screen.findByText('Users sign in with an email address.')).toBeTruthy();
    await userEvent.click(screen.getByRole('tab', { name: 'What changed' }));
    expect(screen.getByText('-Users sign in with a username.')).toBeTruthy();
    expect(getDocumentDiff).toHaveBeenCalledWith('run-1', 'docs/technical_specification.md');
  });

  it('asks for no download, edit and upload, and needs a comment to request changes', async () => {
    const onSubmit = vi.fn();
    render(<ReviewPanel runId="run-1" review={review({ revision: 1 })} onSubmit={onSubmit} />);
    await screen.findByText('Users sign in with an email address.');

    expect(screen.queryByText(/re-upload/i)).toBeNull();
    expect(screen.queryByRole('tab', { name: 'What changed' })).toBeNull();
    const changes = screen.getByRole('button', { name: 'Request changes' }) as HTMLButtonElement;
    expect(changes.disabled).toBe(true);

    await userEvent.type(screen.getByLabelText(/Your comment/), 'Say how a session ends.');
    await userEvent.click(changes);
    expect(onSubmit).toHaveBeenCalledWith('changes', 'Say how a session ends.', undefined);
  });
});
