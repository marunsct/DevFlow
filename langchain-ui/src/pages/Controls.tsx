import { Link } from 'react-router-dom';

/**
 * Every control a person has over a run, in one place (LR.37). Found in the launch review: the owner's controls -
 * instruction injection, the parallel/linear toggle, the sprint summary, work orders, templates, the Sprint Record,
 * the switches and the model diagnosis - were each reachable from a different page, and some from none.
 */
const CONTROLS: { name: string; what: string; where: string; to?: string }[] = [
  { name: 'Directions to a run (instruction injection)', what: 'A note the next model calls of a running run carry, for the rest of the run or for the next stage; on a stopped run, "Resume with a direction".', where: 'A run\'s page: the steering box, or Resume with a direction', to: '/runs' },
  { name: 'Lessons', what: 'What earlier runs learned, offered to later runs\' prompts once approved.', where: 'Settings > Lessons', to: '/settings?tab=lessons' },
  { name: 'Parallel or linear work', what: 'Whether work orders and defect fixes run side by side or one at a time.', where: 'Settings > Models > Behaviour', to: '/settings?tab=models' },
  { name: 'Sprint summary and the Sprint Record', what: 'Each sprint\'s goal, attempts, tests, defects and decisions, as the run went.', where: 'A run\'s page: the sprint summary panel; each sprint\'s record is docs/sprint_N_summary.md, in the handover pack', to: '/runs' },
  { name: 'Work orders', what: 'The plan each sprint is built from: one order per piece of work, with its files and criteria.', where: 'A run\'s page: Artifacts > docs/milestone_plan.md', to: '/runs' },
  { name: 'Document templates', what: 'The templates the specification, plans, reviews and records are written from.', where: 'src/app/doc_templates/templates/ on the server' },
  { name: 'Reviews and involvement', what: 'Which points a run stops at for a person, and whether a waiting review approves itself after a time.', where: 'Home: Your involvement', to: '/' },
  { name: 'Switches', what: 'Optional improvements, on or off for the deployment.', where: 'Admin', to: '/admin' },
  { name: 'Model diagnosis', what: 'A few minutes of checks that decide how the agents are steered for a model.', where: 'Settings > Models: Diagnose this model and set its guidance', to: '/settings?tab=models' },
  { name: 'Pause, resume, rewind, clone, cancel', what: 'Stop a run and continue it, go back to an earlier stage, or start again from its documents.', where: 'A run\'s page, top right', to: '/runs' },
  { name: 'Request a change, download the product', what: 'A new run from a finished product with a change brief; the product\'s files and history as one zip.', where: 'A completed run\'s page', to: '/runs' },
];

export function Controls() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-text-primary">Controls</h1>
      <p className="mt-1 text-sm text-text-secondary">What you can decide about a run, and where.</p>
      <dl className="mt-6 divide-y divide-border rounded-xl border border-border">
        {CONTROLS.map((control) => (
          <div key={control.name} className="px-4 py-3">
            <dt className="text-sm font-semibold text-text-primary">{control.name}</dt>
            <dd className="mt-0.5 text-sm text-text-secondary">{control.what}</dd>
            <dd className="mt-0.5 text-xs text-text-muted">
              {control.to ? <Link to={control.to} className="text-primary hover:underline">{control.where}</Link> : control.where}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
