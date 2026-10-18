import { expect, it, vi } from 'vitest';
import * as Sentry from '@sentry/react';

vi.mock('react-dom/client', () => ({ createRoot: vi.fn(() => ({ render: vi.fn() })) }));
vi.mock('./App.jsx', () => ({ default: () => null }));

it('scrubs Google return values and legacy tokens before Sentry initializes', async () => {
  document.body.innerHTML = '<div id="root"></div>';
  window.history.replaceState({}, '', '/?token=legacy-private-token#google_exchange=private-code&google_state=private-state');
  const observed = [];
  Sentry.init.mockImplementationOnce(() => { observed.push(window.location.href); });
  await import('./main.jsx');
  expect(observed).toEqual([`${window.location.origin}/`]);
  expect(window.location.href).not.toMatch(/legacy-private-token|private-code|private-state/);
});
