import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { buildParent, buildProject } from '../test/factories';
import Projects from './Projects';
import ProjectDetail from './ProjectDetail';

function Location() {
  const location = useLocation();
  const navigate = useNavigate();
  return <><output aria-label="Current location">{location.pathname}{location.search}</output><button onClick={() => navigate(-1)}>Browser back</button></>;
}

function mount(route) {
  localStorage.setItem('abby_auth_token', 'test-token');
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/projects/', () => HttpResponse.json([buildProject({ id: 42, title: 'Birdhouse', status: 'in_progress' })])),
    http.get('*/api/projects/42/', () => HttpResponse.json(buildProject({ id: 42, title: 'Birdhouse' }))),
  );
  return renderWithProviders(<>
    <Location />
    <Routes>
      <Route path="/quests" element={<Projects />} />
      <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
    </Routes>
  </>, { route });
}

describe('Project list return', () => {
  it('returns to the same search, filters and scroll position without forwarding unrelated URL data', async () => {
    const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const y = vi.spyOn(window, 'scrollY', 'get').mockReturnValue(480);
    try {
      const { user } = mount('/quests?tab=ventures&status=in_progress&debug=unrelated');
      await screen.findByRole('button', { name: 'Open Birdhouse' });
      await user.type(screen.getByRole('searchbox', { name: 'Filter projects' }), 'Bird');
      await user.click(screen.getByRole('button', { name: 'Open Birdhouse' }));
      const back = await screen.findByRole('link', { name: 'Back to Projects' });
      expect(back).toHaveAttribute('href', '/quests?tab=ventures&status=in_progress&q=Bird');
      await user.click(back);
      expect(await screen.findByRole('searchbox', { name: 'Filter projects' })).toHaveValue('Bird');
      expect(screen.getByRole('combobox', { name: 'Filter by status' })).toHaveValue('in_progress');
      expect(screen.getByLabelText('Current location')).toHaveTextContent('/quests?tab=ventures&status=in_progress&q=Bird');
      await waitFor(() => expect(scroll).toHaveBeenCalledWith({ top: 480, behavior: 'auto' }));
    } finally {
      scroll.mockRestore();
      y.mockRestore();
    }
  });

  it('a directly opened detail keeps a canonical local list destination', async () => {
    mount('/quests/ventures/42?returnTo=https://other.example/&token=synthetic');
    expect(await screen.findByRole('link', { name: 'Back to Projects' }))
      .toHaveAttribute('href', '/quests?tab=ventures');
  });

  it('browser Back restores the list position as well as its filters', async () => {
    const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const y = vi.spyOn(window, 'scrollY', 'get').mockReturnValue(700);
    try {
      const { user } = mount('/quests?tab=ventures&status=in_progress&q=Bird');
      await user.click(await screen.findByRole('button', { name: 'Open Birdhouse' }));
      await screen.findByRole('link', { name: 'Back to Projects' });
      await user.click(screen.getByRole('button', { name: 'Browser back' }));
      expect(await screen.findByRole('searchbox', { name: 'Filter projects' })).toHaveValue('Bird');
      await waitFor(() => expect(scroll).toHaveBeenCalledWith({ top: 700, behavior: 'auto' }));
    } finally {
      scroll.mockRestore();
      y.mockRestore();
    }
  });
});
