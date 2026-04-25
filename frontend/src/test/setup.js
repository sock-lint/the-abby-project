// Global test setup — executed once per worker before any test file.
//
// jest-dom matchers, browser-API polyfills, Sentry stub, and MSW lifecycle
// hooks live here so each test file stays focused on behavior. Any cleanup
// that must run BETWEEN tests is registered via beforeEach / afterEach.

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, vi } from 'vitest';
import { server } from './server.js';

// --- Sentry stub ----------------------------------------------------------
// The real @sentry/react imports `@sentry/browser`, which in turn needs
// several browser globals and ships its own side effects. Tests never exercise
// Sentry itself; every call site only cares that the function *exists*.
vi.mock('@sentry/react', () => ({
  init: vi.fn(),
  setUser: vi.fn(),
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  addBreadcrumb: vi.fn(),
  ErrorBoundary: ({ children }) => children,
  withErrorBoundary: (C) => C,
}));

// --- Browser API polyfills ------------------------------------------------
// jsdom omits these but app code relies on them via framer-motion, lucide,
// and the image-downscale util.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

if (!window.IntersectionObserver) {
  window.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return []; }
  };
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (!window.createImageBitmap) {
  window.createImageBitmap = vi.fn(async () => ({
    width: 2400,
    height: 1600,
    close: vi.fn(),
  }));
}

// HTMLCanvasElement.getContext / toBlob — jsdom's default getContext returns
// null (no canvas backend), and toBlob isn't implemented. Override both so
// utils/image.js can run in tests.
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function () {
    return { drawImage: () => {} };
  };
  HTMLCanvasElement.prototype.toBlob = function (cb) {
    cb(new Blob(['x'], { type: 'image/jpeg' }));
  };
}

// --- Service Worker / PWA stubs ------------------------------------------
// jsdom doesn't ship a ServiceWorkerContainer. Tests that exercise PWA
// registration mock virtual:pwa-register directly, but a few branches
// touch navigator.serviceWorker for feature detection.
if (!('serviceWorker' in navigator)) {
  Object.defineProperty(navigator, 'serviceWorker', {
    value: {
      register: vi.fn(() => Promise.resolve({})),
      ready: Promise.resolve({}),
      controller: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
    configurable: true,
  });
}

// BeforeInstallPromptEvent isn't a standard jsdom global. Tests for
// useInstallPrompt construct synthetic events that mimic its shape.
if (typeof window.BeforeInstallPromptEvent === 'undefined') {
  window.BeforeInstallPromptEvent = class extends Event {
    constructor(type, init = {}) {
      super(type, init);
      this.platforms = init.platforms || ['web'];
      this.userChoice = init.userChoice || Promise.resolve({ outcome: 'accepted' });
      this.prompt = init.prompt || vi.fn(() => Promise.resolve());
    }
  };
}

// --- Lifecycle ------------------------------------------------------------
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  vi.clearAllMocks();
});

afterAll(() => {
  server.close();
});
