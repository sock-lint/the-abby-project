import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ManagePanel from './ManagePanel.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('ManagePanel', () => {
  it('renders tabs and an initial categories tab', async () => {
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'Science', icon: '🔬' }]} reloadCategories={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole('button').length).toBeGreaterThan(0));
  });

  it('switches to subjects tab', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/subjects/', () =>
        HttpResponse.json([{ id: 1, name: 'Math', category: 1 }]),
      ),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
    );
    render(<ManagePanel categories={[{ id: 1, name: 'C' }]} reloadCategories={vi.fn()} />);
    const subjectsTab = await screen.findByRole('button', { name: /subjects/i });
    await user.click(subjectsTab);
    await waitFor(() => expect(screen.getByText('Math')).toBeInTheDocument());
  });
});
