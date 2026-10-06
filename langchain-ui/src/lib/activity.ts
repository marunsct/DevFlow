/**
 * Plain-English descriptions of what the workflow is doing.
 *
 * Everything a run emits is named for the code that produced it -
 * `specialist_backend_0`, `write_artifact`, `waiting_for_approval`. Those names
 * are precise and they are useless to someone who did not build this. This
 * module is the single place where they become sentences a person can read, so
 * the dashboard never has to show a raw identifier.
 */

export interface StageCopy {
  /** A short title, sentence case, no jargon. */
  title: string;
  /** One line saying what actually happens here, in plain words. */
  blurb: string;
}

/**
 * Stage copy keyed by the backend's stage name.
 *
 * Written for someone who has never seen the pipeline: no role titles, no
 * "artifacts", no "agents". "Working out what you're building" beats "Product
 * Manager", because the reader cares what is happening, not who does it.
 */
const STAGE_COPY: Record<string, StageCopy> = {
  product_manager: {
    title: 'Understanding your product',
    blurb: 'Reading your document to work out what you want built and who it is for.',
  },
  tools_models: {
    title: 'Comparing the options',
    blurb: 'Weighing up the technologies and AI models that would suit this product.',
  },
  stack_selector: {
    title: 'Choosing the technology',
    blurb: 'Settling on the languages, frameworks and services the build will use.',
  },
  specialist_consultation: {
    title: 'Asking the specialists',
    blurb: "Getting the interface, data and service specialists' advice before the technical plan is written.",
  },
  principal_architect: {
    title: 'Designing how it works',
    blurb: 'Writing the technical plan: the pieces, the data, and how they fit together.',
  },
  architecture_review: {
    title: 'Checking the design',
    blurb: 'A second opinion on the plan, looking for security holes and things that will not work.',
  },
  user_review_specification: {
    title: 'Your review',
    blurb: 'Paused for you to read the technical plan and say whether to continue.',
  },
  scrum_master: {
    title: 'Planning the work',
    blurb: 'Splitting the design into sprints small enough to build one at a time.',
  },
  technical_lead: {
    title: 'Setting up the next chunk',
    blurb: 'Picking what to build first and breaking it into individual tasks.',
  },
  specialist_dispatch: {
    title: 'Building it',
    blurb: 'Writing the actual code and tests for this piece of the product.',
  },
  test_and_triage: {
    title: 'Testing',
    blurb: 'Running the tests and writing down anything that failed.',
  },
  defect_remediation: {
    title: 'Fixing what broke',
    blurb: 'Sending each problem back to be fixed, then testing again.',
  },
  security_review: {
    title: 'Security check',
    blurb: 'Looking over the finished code for anything unsafe.',
  },
  advice_review: {
    title: "Checking the specialists' advice",
    blurb: 'Each specialist asked before the design checks its advice was built this sprint.',
  },
  acceptance_dispute: {
    title: 'Judging the failing tests',
    blurb: 'Before a failed sprint is planned again, the QA lead says which locked tests no right product could pass.',
  },
  milestone_review: {
    title: 'Reviewing the work',
    blurb: 'Checking the finished piece against what was planned.',
  },
  user_review_sprint: {
    title: 'Your review',
    blurb: 'Paused for you to look at the completed sprint and say whether to continue.',
  },
  sprint_advance: {
    title: 'Starting the next sprint',
    blurb: 'This chunk is done. Moving on to the next one.',
  },
  complete: {
    title: 'Finished',
    blurb: 'Everything ran through to the end. The results are ready below.',
  },
  failed: {
    title: 'Stopped',
    blurb: 'Something went wrong and the run needs a person to look at it.',
  },
};

/** Specialist stages are numbered per task (`specialist_backend_0`). */
const SPECIALIST_COPY: Record<string, StageCopy> = {
  backend: { title: 'Building the backend', blurb: 'Writing the server code, data models and APIs.' },
  frontend: { title: 'Building the interface', blurb: 'Writing the screens people will actually click on.' },
  ui_ux: { title: 'Designing the interface', blurb: 'Laying out the screens and how someone moves between them.' },
  testing: { title: 'Writing tests', blurb: 'Writing checks that prove the code does what it should, and running them.' },
  devops: { title: 'Setting up deployment', blurb: 'Making the project buildable and runnable outside a laptop.' },
  security: { title: 'Hardening security', blurb: 'Closing gaps that would let the wrong person in.' },
  data: { title: 'Working on the data layer', blurb: 'Shaping how information is stored and retrieved.' },
};

const titleCase = (raw: string) =>
  raw.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).trim();

/**
 * Describe any stage name, including ones this file has never seen.
 *
 * An unknown stage still has to render as something readable, so the fallback
 * turns `some_new_stage` into "Some New Stage" rather than showing the raw
 * identifier or, worse, an empty row.
 */
export function describeStage(rawName: string | null | undefined): StageCopy {
  if (!rawName) return { title: 'Getting started', blurb: 'Setting up the run.' };

  // Pause stages are named after the stage they are waiting on.
  const name = rawName.replace(/^awaiting_(approval|user_review):/, '');

  if (STAGE_COPY[name]) return STAGE_COPY[name];

  const specialist = /^specialist_(.+?)(?:_\d+)?$/.exec(name);
  if (specialist) {
    const role = specialist[1];
    return (
      SPECIALIST_COPY[role] ?? {
        title: `Building the ${role.replace(/_/g, ' ')} part`,
        blurb: 'Writing code and tests for this piece of the product.',
      }
    );
  }

  return { title: titleCase(name), blurb: 'Working through this step.' };
}

export interface StatusCopy {
  label: string;
  tone: 'done' | 'active' | 'waiting' | 'error' | 'idle';
}

/**
 * Status copy, in the words a person would use.
 *
 * "Waiting for you" instead of `waiting_for_approval` matters most: it is the
 * only status that is a request, and the old label read like a state machine
 * rather than something the reader has to act on.
 */
export function describeStatus(status: string | null | undefined): StatusCopy {
  switch (status) {
    case 'completed':
    case 'approved':
      return { label: 'Done', tone: 'done' };
    case 'approved_with_notes':
      return { label: 'Done, with notes', tone: 'done' };
    case 'running':
      return { label: 'Working on it', tone: 'active' };
    case 'waiting_for_approval':
      return { label: 'Waiting for you', tone: 'waiting' };
    case 'waiting_for_review':
      return { label: 'Needs your review', tone: 'waiting' };
    case 'paused':
      return { label: 'Paused', tone: 'waiting' };
    case 'rejected':
      return { label: 'Sent back for changes', tone: 'error' };
    case 'failed':
      return { label: 'Stopped', tone: 'error' };
    case 'cancelled':
      return { label: 'Cancelled', tone: 'idle' };
    case 'created':
      return { label: 'Not started yet', tone: 'idle' };
    default:
      return { label: 'Up next', tone: 'idle' };
  }
}

export interface ActionCopy {
  /** What happened, as a sentence: "Saved the product summary". */
  summary: string;
  /** The file or search term involved, when there is one. */
  target?: string;
  /** Broad kind, used only to pick an icon. */
  kind: 'write' | 'read' | 'search' | 'run' | 'think';
  /** Which part of the file was touched: "lines 120-180". */
  range?: string;
}

/**
 * Pull a quoted value out of a tool call's argument blob.
 *
 * The blob is a Python dict repr, not JSON, so it is matched rather than
 * parsed. A miss just means the sentence loses its filename, which is fine.
 */
const arg = (raw: string, key: string): string | undefined => {
  const match = new RegExp(`['"]${key}['"]\\s*:\\s*['"]([^'"]*)['"]`).exec(raw);
  return match?.[1] || undefined;
};

/**
 * Pull a numeric value out of a tool call's argument blob.
 *
 * `arg` only matches quoted values, so `start_line` and `line_count` - which
 * arrive unquoted, being integers - were invisible to it. A partial read
 * therefore narrated identically to a whole-file read.
 */
const numArg = (raw: string, key: string): number | undefined => {
  const match = new RegExp(`['"]${key}['"]\\s*:\\s*(\\d+)`).exec(raw);
  return match ? Number(match[1]) : undefined;
};

const fileName = (path?: string) => (path ? path.split('/').pop() || path : undefined);

/** "lines 120-180", or "from line 120" when the end is not yet known. */
const lineRange = (start?: number, end?: number): string | undefined => {
  if (start === undefined) return undefined;
  if (end === undefined || end <= start) return `from line ${start.toLocaleString()}`;
  return `lines ${start.toLocaleString()}-${end.toLocaleString()}`;
};

/**
 * Turn one tool call into a sentence about what the run just did.
 *
 * The panel this feeds is meant to read like someone narrating their work, so
 * every branch produces plain past tense with no tool names in it. Unknown
 * tools fall back to the tool's own name rather than being dropped, because a
 * silent gap in a progress feed is worse than an awkward sentence.
 */
export function describeAction(toolName: string, rawArgs: string): ActionCopy {
  const tool = (toolName || '').toLowerCase();

  if (tool === 'write_artifact') {
    const path = arg(rawArgs, 'relative_path');
    return { summary: `Saved ${fileName(path) ?? 'a document'}`, target: path, kind: 'write' };
  }
  if (tool === 'edit_artifact' || tool === 'edit_file') {
    const path = arg(rawArgs, 'relative_path') ?? arg(rawArgs, 'file_path');
    return { summary: `Revised ${fileName(path) ?? 'a document'}`, target: path, kind: 'write' };
  }
  if (tool === 'read_repository_file' || tool === 'read_file') {
    const path = arg(rawArgs, 'relative_path') ?? arg(rawArgs, 'file_path');
    // `read_repository_file` takes start_line/line_count; the built-in
    // `read_file` takes offset/limit. Both mean "part of this file", and a
    // reader watching an agent work through a long specification wants to see
    // which part - that is the difference between "it is reading" and "it is
    // three-quarters of the way through".
    const start = numArg(rawArgs, 'start_line') ?? numArg(rawArgs, 'offset');
    const count = numArg(rawArgs, 'line_count') ?? numArg(rawArgs, 'limit');
    const end = start !== undefined && count !== undefined ? start + count - 1 : undefined;
    const partial = start !== undefined || count !== undefined;
    return {
      summary: `${partial ? 'Reading part of' : 'Read'} ${fileName(path) ?? 'a file'}`,
      target: path,
      kind: 'read',
      // Only a partial read has a range worth stating. Labelling a whole-file
      // read "from line 1" says nothing and implies it stopped somewhere.
      range: partial ? lineRange(start ?? 1, end) : undefined,
    };
  }
  if (tool === 'inspect_repository') {
    return { summary: 'Looked over the project so far', kind: 'read' };
  }
  if (tool === 'ls') {
    const path = arg(rawArgs, 'path');
    return { summary: 'Listed what is in the project', target: path, kind: 'read' };
  }
  if (tool === 'glob') {
    const pattern = arg(rawArgs, 'pattern');
    return { summary: `Looked for files matching ${pattern ?? 'a pattern'}`, target: pattern, kind: 'search' };
  }
  if (tool === 'grep') {
    const pattern = arg(rawArgs, 'pattern');
    return { summary: `Searched the project for "${pattern ?? 'a phrase'}"`, target: pattern, kind: 'search' };
  }
  if (tool === 'run_terminal_command' || tool === 'execute') {
    const command = /\[([^\]]*)\]/.exec(rawArgs)?.[1]?.replace(/['"]/g, '') ?? '';
    return { summary: command ? `Ran ${command}` : 'Ran a command', target: command, kind: 'run' };
  }
  if (tool === 'run_validation') {
    return { summary: 'Ran the tests', kind: 'run' };
  }
  if (tool === 'task') {
    return { summary: 'Asked a helper to dig into something', kind: 'think' };
  }

  return { summary: titleCase(tool || 'Did something'), kind: 'think' };
}

/**
 * The path a tool result reports it actually touched, if any.
 *
 * The call's own arguments are not reliable for this. Agents emit `content`
 * before `relative_path` about half the time, and the event is clipped for
 * length before publishing, so the path is simply not in the message - which is
 * how a write of `docs/architecture_review.md` came to be narrated as "Saved a
 * document". The result is both shorter and authoritative: it says what was
 * written rather than what was asked for.
 */
export function pathFromResult(message: string): string | undefined {
  const match = /["']?(?:path|file_path)["']?\s*:\s*["']([^"']+)["']/.exec(message || '');
  return match?.[1] || undefined;
}

/**
 * What a partial read actually returned, taken from the tool's own result.
 *
 * The call says what was asked for; the result says what came back, which is
 * not the same thing when the request runs past the end of the file. It also
 * carries `total_lines`, so the feed can say "lines 1-200 of 1,412" - the only
 * form that tells a reader how much of a document an agent has actually seen.
 *
 * Returns undefined for a whole-file read, which has no range to report.
 */
export function readRangeFromResult(message: string): string | undefined {
  const raw = message || '';
  const num = (key: string): number | undefined => {
    const match = new RegExp(`['"]${key}['"]\\s*:\\s*(\\d+)`).exec(raw);
    return match ? Number(match[1]) : undefined;
  };
  const start = num('start_line');
  const end = num('end_line');
  const total = num('total_lines');
  if (start === undefined || end === undefined) return undefined;
  const span = `lines ${start.toLocaleString()}-${end.toLocaleString()}`;
  return total === undefined ? span : `${span} of ${total.toLocaleString()}`;
}

/**
 * Shorten a path for display without losing which file it is.
 *
 * Tools are handed absolute host paths, so a target could be 90 characters of
 * `/app/data/workspaces/thehub-run-<uuid>/...` before reaching the part that
 * identifies the file. The last two segments carry the meaning.
 */
export function shortenPath(path: string): string {
  const parts = path.split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join('/')}`;
}

/**
 * Split a `tool_call` message into its tool name and argument blob.
 *
 * The event is published as `"<name>: <args>"`. `metadata.tool` carries the
 * name too and is preferred; this is the fallback for older events that
 * predate that metadata.
 */
export function splitToolMessage(message: string): { tool: string; args: string } {
  const separator = message.indexOf(':');
  if (separator === -1) return { tool: message.trim(), args: '' };
  return {
    tool: message.slice(0, separator).trim(),
    args: message.slice(separator + 1).trim(),
  };
}
