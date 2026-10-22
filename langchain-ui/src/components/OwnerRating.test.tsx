import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { OwnerRating } from './OwnerRating';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn() } }));
vi.mock('../api', () => ({ api }));

describe('the owner rating', () => {
  it('rates the delivered run with one choice and keeps the line given', async () => {
    api.get.mockResolvedValue({ data: null });
    api.put.mockResolvedValue({ data: { score: 4, note: 'clean' } });
    render(<OwnerRating runId="run-1" />);

    fireEvent.change(screen.getByLabelText('One line on the product'), { target: { value: 'clean' } });
    fireEvent.click(screen.getByLabelText('4 of 5'));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/runs/run-1/rating', { score: 4, note: 'clean' }));
    expect(await screen.findByText('saved: 4 of 5')).toBeTruthy();
  });
});
