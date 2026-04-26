import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import AtlasHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/atlas" element={<AtlasHub />} />
          <Route path="/chronicle" element={<LocationProbe />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname + loc.search}</div>;
}

describe('AtlasHub', () => {
  it('renders the Atlas hub with the Skills tab default', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
    );
    renderAt('/atlas');
    await waitFor(() => expect(screen.getByText('Atlas')).toBeInTheDocument());
    expect(screen.getAllByText(/skills/i).length).toBeGreaterThan(0);
  });

  it('no longer exposes Sketchbook or Yearbook in its tab strip', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
    );
    renderAt('/atlas');
    await waitFor(() => expect(screen.getByText('Atlas')).toBeInTheDocument());
    const tablist = screen.getByRole('tablist');
    expect(tablist).not.toHaveTextContent(/sketchbook/i);
    expect(tablist).not.toHaveTextContent(/yearbook/i);
  });

  it('redirects /atlas?tab=sketchbook to /chronicle?tab=sketchbook', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    renderAt('/atlas?tab=sketchbook');
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/chronicle?tab=sketchbook'),
    );
  });

  it('redirects /atlas?tab=yearbook to /chronicle?tab=yearbook', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    renderAt('/atlas?tab=yearbook');
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/chronicle?tab=yearbook'),
    );
  });
});
