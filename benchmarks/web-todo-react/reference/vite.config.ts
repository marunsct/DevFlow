import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Relative asset paths, so the built page works from any directory a static server serves.
export default defineConfig({ plugins: [react()], base: './' });
