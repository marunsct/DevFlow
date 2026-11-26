import { serve } from '@hono/node-server';
import type { Hono } from 'hono';
import * as entry from './app.ts';

const port = Number(process.env.PORT || 3000);
const hostname = process.env.HOST || '127.0.0.1';
// The named `createApp`, or the module's default export, awaited: a factory written either way, or returning a
// Promise, is served all the same. It is handed `DATA_DIR`, which a factory that takes no argument ignores.
const exported = entry as unknown as Record<string, unknown>;
const factory = (exported.createApp ?? exported.default) as (dataDir?: string) => Hono | Promise<Hono>;
const app = await factory(process.env.DATA_DIR);

serve({ fetch: app.fetch, port, hostname }, () => {
  console.log(`Listening on http://${hostname}:${port}`);
});
