import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import JournalReader from './JournalReader.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildUser, buildParent } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function summaryPayload(entries) {
  // Wrap entries in a single-chapter summary (the shape Yearbook reads).
  return {
    chapters: [
      { chapter_year: 2025, label: 'Chapter 2025–26', is_current: true, stats: {}, entries },
    ],
    current_chapter_year: 2025,
  };
}

function renderReader() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <JournalReader />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('JournalReader — child view', () => {
  it('renders existing journal entries newest-first and skips other kinds', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json(summaryPayload([
          { id: 10, kind: 'journal',  occurred_on: '2026-04-10', title: 'Earlier',  summary: 'older entry', is_private: true },
          { id: 11, kind: 'birthday', occurred_on: '2026-04-15', title: 'Birthday', summary: '', is_private: false },
          { id: 12, kind: 'journal',  occurred_on: '2026-04-20', title: 'Today',    summary: 'newer entry', is_private: true },
        ])),
      ),
    );

    renderReader();

    await waitFor(() => expect(screen.getByText('Today')).toBeInTheDocument());
    expect(screen.getByText('Earlier')).toBeInTheDocument();
    expect(screen.queryByText('Birthday')).toBeNull();

    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(titles.indexOf('Today')).toBeLessThan(titles.indexOf('Earlier'));
  });

  it('child view does NOT show the lock chip on private entries', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json(summaryPayload([
          { id: 1, kind: 'journal', occurred_on: '2026-04-10', title: 'Mine', summary: 'secret words', is_private: true },
        ])),
      ),
    );

    renderReader();

    await waitFor(() => expect(screen.getByText('Mine')).toBeInTheDocument());
    expect(screen.queryByText(/private/i)).toBeNull();
  });

  it('renders empty-state when child has no entries yet', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/chronicle/summary/', () => HttpResponse.json(summaryPayload([]))),
    );

    renderReader();

    await waitFor(() => expect(screen.getByText(/no entries yet/i)).toBeInTheDocument());
    expect(screen.getByText(/Write your first entry above/i)).toBeInTheDocument();
  });

  it('shows "Write today’s entry" when no entry exists, and POSTs the body', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/chronicle/summary/', () => HttpResponse.json(summaryPayload([]))),
      http.get('*/api/chronicle/journal/today/', () => new HttpResponse(null, { status: 204 })),
    );
    const create = spyHandler('post', /\/api\/chronicle\/journal\/$/, {
      id: 99, kind: 'journal', is_private: true, title: 'Hello', summary: 'world',
    });
    server.use(create.handler);

    const user = userEvent.setup();
    renderReader();

    const writeBtn = await screen.findByRole('button', { name: /write today’s entry/i });
    await user.click(writeBtn);

    // BottomSheet portals into document.body — query off body.
    const dialog = await within(document.body).findByRole('dialog', {
      name: /write in your journal/i,
    });
    await user.type(within(dialog).getByLabelText(/title/i), 'Hello');
    await user.type(within(dialog).getByLabelText(/what's on your mind/i), 'world');
    await user.click(within(dialog).getByRole('button', { name: /save entry/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toEqual({ title: 'Hello', summary: 'world' });
    expect(create.calls[0].url).toMatch(/\/chronicle\/journal\/$/);
  });

  it('shows "Edit today’s entry" when today\'s entry already exists', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/chronicle/summary/', () => HttpResponse.json(summaryPayload([]))),
      http.get('*/api/chronicle/journal/today/', () =>
        HttpResponse.json({
          id: 50, kind: 'journal', is_private: true, title: 'A title', summary: 'a body',
        }),
      ),
    );

    renderReader();

    expect(await screen.findByRole('button', { name: /edit today’s entry/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /write today’s entry/i })).toBeNull();
  });
});

describe('JournalReader — parent view', () => {
  it('renders the child picker and never shows the write button', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () =>
        HttpResponse.json([{ id: 7, first_name: 'Abby', username: 'abby' }]),
      ),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json(summaryPayload([
          { id: 1, kind: 'journal', occurred_on: '2026-04-10', title: 'Hers', summary: 'secret words', is_private: true },
        ])),
      ),
    );

    renderReader();

    await waitFor(() => expect(screen.getByText('Hers')).toBeInTheDocument());
    expect(screen.getByLabelText(/reading/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /write today’s entry/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /edit today’s entry/i })).toBeNull();
    // Lock chip IS visible to the parent on the child's private entry.
    expect(screen.getByText(/private/i)).toBeInTheDocument();
  });

  it('renders no-children empty-state when parent has no children', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
    );

    renderReader();

    await waitFor(() => expect(screen.getByText(/no children yet/i)).toBeInTheDocument());
  });
});
