import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import CodexPage from './CodexPage.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('CodexPage', () => {
  it('names the surface it actually administers, not "Codex"', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    renderWithProviders(<CodexPage />);

    // "Codex" was ambiguous — the Bestiary hub ships a kid-facing Codex tab
    // for species, and this page administers neither that nor the Lorebook.
    expect(
      await screen.findByRole('heading', { name: /content catalog/i, level: 1 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /^codex$/i })).toBeNull();
  });
});
