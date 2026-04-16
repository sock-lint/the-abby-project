import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Separate from vite.config.js so test-only concerns (jsdom, coverage, MSW
// setup) don't leak into production builds. @vitejs/plugin-react is re-added
// here because the build pipeline needs JSX transform during tests too.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // index.css imports Tailwind 4 via @plugin syntax that vitest can't parse;
    // disabling CSS processing in tests has no observable effect on behavior.
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.{js,jsx}'],
      exclude: [
        // Entry points + theme utility are thin IO glue, not logic.
        'src/main.jsx',
        'src/themes.js',
        // Dev-only design showcase, gated by window.location in App.jsx.
        'src/pages/__design.jsx',
        // Decorative SVG libraries — no branches to cover.
        'src/components/icons/JournalIcons.jsx',
        'src/components/journal/StreakFlame.jsx',
        'src/components/journal/DeckleDivider.jsx',
        'src/components/journal/PageTurnTransition.jsx',
        // Static asset re-exports and motion helper bag.
        'src/assets/**',
        'src/motion/**',
        // The test scaffolding itself.
        'src/test/**',
        'src/**/*.test.{js,jsx}',
      ],
      // Coverage floor — the initial test scaffolding lands at ~70% lines
      // and ~65% branches. Holding the gate slightly below so follow-up
      // merges that touch untested branches don't slip past, while leaving
      // headroom to tighten upward as coverage grows.
      thresholds: {
        lines: 65,
        branches: 55,
        functions: 55,
        statements: 65,
      },
    },
  },
});
