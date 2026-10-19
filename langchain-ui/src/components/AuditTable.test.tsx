import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { AuditTable } from './AuditTable';

const row = (stage: string, extra: Record<string, number> = {}) => ({
  stage, wall_seconds: 600, model_seconds: 500, model_calls: 10, input_tokens: 500_000, cached_tokens: 300_000,
  output_tokens: 20_000, lost_replies: 0, tool_calls: 12, tool_failures: 1, redundant_reads: 2, ...extra,
});

vi.mock('../api', () => ({
  getUsage: vi.fn(async () => ({
    stages: [row('principal_architect', { model_seconds: 1400, output_tokens: 188_900 }), row('defect_fix_1_1', { tool_failures: 11, tool_calls: 46 })],
  })),
}));

describe('the audit tab', () => {
  it('lists each stage and marks the worst cell of each column', async () => {
    render(<AuditTable runId="run-1" refreshKey="k" />);

    const rows = await screen.findAllByRole('row');
    expect(rows).toHaveLength(3);
    const architect = rows[1];
    expect(within(architect).getByText('23 min').className).toMatch(/text-warning/);
    expect(within(architect).getByText('188.9 k').className).toMatch(/text-warning/);
    expect(within(rows[2]).getByText('11/46').className).toMatch(/text-warning/);
    expect(screen.getAllByText('(the most of any stage)').length).toBeGreaterThan(2);
  });
});
