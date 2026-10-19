import { useRef, useState } from 'react';
import { Bell, Inbox, Plus, Search } from 'lucide-react';
import {
  Badge, Button, Card, Checkbox, Dialog, Drawer, EmptyState, IconButton, InfoRow, Input, Kbd,
  Progress, Select, Skeleton, Stat, StatusBadge, Tabs, Textarea, Tooltip,
} from '../ui';
import { ThemeToggle } from '../components/ThemeToggle';
import { InboxPanel } from '../components/NeedsYouInbox';
import type { RunSummary } from '../types';

const sampleRun = (run_id: string, status: string, current_stage: string, extra: Partial<RunSummary> = {}): RunSummary => ({
  run_id, status, current_stage, created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T01:00:00Z', document_names: [],
  delivery_mode: 'fast', local_only: true, completion_gaps: 0, criteria_proven: null, criteria_total: null, gate_deadline: null, ...extra,
});

const INBOX_WAITING = [
  sampleRun('run-8b0c41d2-5e1f', 'waiting_for_review', 'release_review', { gate_deadline: '2026-10-19T00:40:00Z' }),
  sampleRun('run-1f2e3d4c-9a8b', 'waiting_for_approval', 'awaiting_approval:specification'),
  sampleRun('run-77aa01bc-0c0d', 'waiting_for_budget', 'defect_fix_2'),
];
const INBOX_STOPPED = [sampleRun('run-c3d4e5f6-1234', 'failed', 'acceptance_tests')];

/**
 * Every primitive of the kit on one page, in its states - the "kitchen sink"
 * the accessibility measure and the theme screenshots read. Served by the dev
 * build only (`/dev/ui`).
 */
export function DevUI() {
  const [dialog, setDialog] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null);
  return (
    <main className="mx-auto max-w-5xl space-y-8 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary">Component kit</h1>
        <ThemeToggle />
      </header>

      <Card>
        <Card.Header title="Buttons" />
        <Card.Body className="flex flex-wrap items-center gap-3">
          <Button variant="primary" icon={<Plus className="h-4 w-4" />}>Start a build</Button>
          <Button>Secondary</Button>
          <Button variant="quiet">Quiet</Button>
          <Button variant="danger">Cancel the run</Button>
          <Button variant="primary" loading>Saving</Button>
          <Button size="sm">Small</Button>
          <IconButton label="Search runs" icon={<Search className="h-4 w-4" />} />
          <Tooltip text="Runs waiting for you"><IconButton label="Needs you" icon={<Bell className="h-4 w-4" />} /></Tooltip>
        </Card.Body>
      </Card>

      <Card>
        <Card.Header title="Badges and status" />
        <Card.Body className="flex flex-wrap gap-2">
          {['running', 'waiting_for_approval', 'paused', 'completed', 'failed', 'cancelled'].map((status) => (
            <StatusBadge key={status} status={status} />
          ))}
          <Badge tone="accent">fast</Badge>
          <Badge tone="warn">3 gaps</Badge>
        </Card.Body>
      </Card>

      <Card>
        <Card.Header title="Fields" />
        <Card.Body className="grid gap-4 sm:grid-cols-2">
          <Input label="Run name" hint="Shown in the runs list" placeholder="notes-api" />
          <Input label="Model" error="This model is not served at that address" defaultValue="unknown-model" />
          <Select label="Delivery" defaultValue="fast">
            <option value="fast">Fast</option>
            <option value="thorough">Thorough</option>
          </Select>
          <Textarea label="Brief" hint="What the product must do" />
          <Checkbox label="Approve each gate myself" hint="The run pauses at every gate until you answer" />
        </Card.Body>
      </Card>

      <Card>
        <Card.Header title="Tabs" />
        <Card.Body>
          <Tabs label="Run sections" items={[
            { id: 'work', label: 'Work', content: <p className="text-sm text-text-secondary">The stage at work.</p> },
            { id: 'changes', label: 'Changes', content: <p className="text-sm text-text-secondary">What the run changed.</p> },
            { id: 'evidence', label: 'Evidence', content: <p className="text-sm text-text-secondary">What proves it.</p> },
          ]} />
        </Card.Body>
      </Card>

      <Card>
        <Card.Header title="Numbers, progress, loading, nothing yet" />
        <Card.Body className="space-y-6">
          <dl className="grid grid-cols-3 gap-4">
            <Stat label="Criteria proven" value="9 of 12" source="the locked suite, measured 14:02" />
            <Stat label="Model time" value="35 min" source="the run's transcript" />
            <Stat label="Cached input" value="59%" source="the server's usage report" />
          </dl>
          <Progress label="Sprint 2 of 3" value={2} max={3} />
          <Progress label="Waiting for the model" />
          <Skeleton lines={3} />
          <EmptyState icon={<Inbox className="h-6 w-6" />} title="No runs yet." action={<Button variant="primary">Start a build</Button>} />
          <dl><InfoRow label="Delivery" value="fast" /><InfoRow label="Shortcut" value={<Kbd>?</Kbd>} /></dl>
        </Card.Body>
      </Card>

      <Card>
        <Card.Header title="Needs-you inbox" />
        <Card.Body className="max-w-md rounded-xl border border-border bg-surface-raised p-3">
          <InboxPanel
            waiting={INBOX_WAITING}
            stopped={INBOX_STOPPED}
            answering={null}
            onApprove={() => undefined}
            onOpen={() => undefined}
            onLeave={() => undefined}
            onDismiss={() => undefined}
            notifying={false}
            onNotifying={() => undefined}
          />
        </Card.Body>
      </Card>

      <Card>
        <Card.Header title="Dialog and drawer" />
        <Card.Body className="flex gap-3">
          <Button onClick={() => setDialog(true)}>Open a dialog</Button>
          <Button onClick={() => setDrawer(true)}>Open a drawer</Button>
        </Card.Body>
      </Card>
      <Dialog
        open={dialog}
        onClose={() => setDialog(false)}
        title="Cancel this run?"
        description="It stops at the next stage boundary; its work so far is kept."
        initialFocus={cancel}
        footer={<>
          <Button ref={cancel} onClick={() => setDialog(false)}>Keep it running</Button>
          <Button variant="danger" onClick={() => setDialog(false)}>Cancel the run</Button>
        </>}
      />
      <Drawer open={drawer} onClose={() => setDrawer(false)} title="routes.ts" footer={<Button onClick={() => setDrawer(false)}>Close</Button>}>
        <pre className="rounded-lg bg-code p-3 text-xs text-code-fg">export const routes = new Hono();</pre>
      </Drawer>
    </main>
  );
}
