import { Hono } from 'hono';
import type { Context } from 'hono';
import * as store from './store.ts';
import { defineRoutes } from './routes.ts';

export function createApp(dataDir?: string): Hono {
  const appDataDir = dataDir || process.env.DATA_DIR;
  const currentStore = store.loadStore(appDataDir);

  const app = new Hono();

  defineRoutes(app, currentStore);

  app.onError((err, c: Context) => {
    console.error(err);
    return c.json({ error: 'Internal server error' }, 500);
  });

  return app;
}
