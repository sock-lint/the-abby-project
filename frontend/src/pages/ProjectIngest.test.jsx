import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ProjectIngest from './ProjectIngest.jsx';
import { server } from '../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectIngest />
    </MemoryRouter>,
  );
}

describe('ProjectIngest', () => {
  it('renders the source step with URL/PDF tabs', async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getAllByText((t) => /url|pdf|source|ingest|import/i.test(t)).length,
      ).toBeGreaterThan(0),
    );
  });

  it('opens exactly one ingestion job however many times Parse Source is tapped', async () => {
    // Each job runs the paid LLM enrichment pipeline server-side, so a
    // double-tap during the in-flight POST must not queue a second one.
    let starts = 0;
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    server.use(
      http.post('*/api/projects/ingest/', async () => {
        starts += 1;
        await gate;
        return HttpResponse.json({ id: 3, status: 'pending' }, { status: 201 });
      }),
      http.get('*/api/projects/ingest/3/', () =>
        HttpResponse.json({ id: 3, status: 'pending' }),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await user.type(
      document.querySelector('input[type="url"]'),
      'https://www.instructables.com/thing',
    );
    const start = screen.getByRole('button', { name: /parse source/i });
    await user.click(start);

    // Button flips to its in-flight state and stops accepting taps.
    const busy = await screen.findByRole('button', { name: /reading/i });
    expect(busy).toBeDisabled();
    await user.click(busy);

    release();
    await waitFor(() => expect(screen.getByText(/reading the steps/i)).toBeInTheDocument());
    expect(starts).toBe(1);
  });
});
