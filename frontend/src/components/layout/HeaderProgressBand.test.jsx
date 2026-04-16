import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HeaderProgressBand from './HeaderProgressBand';
import { server } from '../../test/server';

describe('HeaderProgressBand', () => {
  it('renders an inert divider when no quest is active', async () => {
    server.use(http.get('*/api/quests/active/', () => HttpResponse.json(null)));
    render(
      <MemoryRouter>
        <HeaderProgressBand />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.queryByRole('button')).not.toBeInTheDocument());
  });

  it('renders a progress-scaled button when a quest is active', async () => {
    server.use(
      http.get('*/api/quests/active/', () =>
        HttpResponse.json({
          id: 9, status: 'active',
          progress_percent: 62, current_progress: 6, effective_target: 10,
          definition: { name: 'Boss: Moblin' },
        }),
      ),
    );
    render(
      <MemoryRouter>
        <HeaderProgressBand />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /boss: moblin · 62% complete/i })).toBeInTheDocument(),
    );
  });
});
