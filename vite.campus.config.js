import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'campus',
  plugins: [react()],
  build: {
    outDir: '../dist-campus',
    emptyOutDir: true,
  },
});
