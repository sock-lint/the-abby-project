import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildProject, buildUser } from '../../test/factories';
import { setToken } from '../../api/client';
import ProjectDetail from '../ProjectDetail';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderMaterials({ user = buildUser(), requests = [] } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    http.get('*/api/projects/42/', () => HttpResponse.json(buildProject({ id: 42, title: 'Bird feeder' }))),
    http.get('*/api/print-requests/', () => HttpResponse.json(requests)),
  );
  return renderWithProviders(<ProjectDetail />, { route: '/quests/ventures/42', routePath: '/quests/ventures/:id' });
}

const print = {
  id: 7, title: 'Perch', user: 1, user_name: 'Abby', status: 'pending',
  project: 42, project_title: 'Bird feeder', reason: 'For the feeder',
};

describe('project print requests in Materials', () => {
  it('requests a project part through the shared print form and tracks the confirmed request', async () => {
    const { user } = renderMaterials();
    const requested = spyHandler('post', /\/api\/print-requests\/$/, { ...print });
    server.use(requested.handler,
      http.get('*/api/print-budgets/', () => HttpResponse.json([
        { user: 2, minutes_per_coin: 1 }, { user: 1, minutes_per_coin: 15 },
      ])),
    );
    await user.click(await screen.findByRole('tab', { name: 'Materials' }));
    await user.click(await screen.findByRole('button', { name: 'Request a part' }));
    const dialog = screen.getByRole('dialog', { name: 'Ask for a print' });
    expect(within(dialog).getByText('For project: Bird feeder')).toBeInTheDocument();
    expect(await within(dialog).findByText(/Prints cost 1 coin per 15 estimated print minutes/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Link to the model'), 'https://example.com/perch');
    await user.type(within(dialog).getByLabelText('What is it?'), 'Perch');
    await user.type(within(dialog).getByLabelText('Colour'), 'green');
    await user.type(within(dialog).getByLabelText('Why do you want it?'), 'For the feeder');
    await user.click(within(dialog).getByRole('button', { name: 'Send request' }));
    await waitFor(() => expect(requested.calls).toHaveLength(1));
    expect(requested.calls[0].body).toEqual({
      title: 'Perch', source_url: 'https://example.com/perch', color: 'green',
      reason: 'For the feeder', needed_by: null, project_id: 42,
    });
    expect(await screen.findByText('Perch')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View all 3D prints' })).toHaveAttribute('href', '/treasury?tab=forge');
  });

  it('loads later project pages without losing the project filter or older parts', async () => {
    const { user } = renderMaterials();
    const reads = [];
    server.use(http.get('*/api/print-requests/', ({ request }) => {
      const query = new URL(request.url).searchParams;
      reads.push({ project: query.get('project_id'), page: query.get('page') });
      return HttpResponse.json(query.get('page') === '2'
        ? { count: 2, results: [{ ...print, id: 8, title: 'Latch', status: 'completed' }], next: null }
        : { count: 2, results: [print], next: '/api/print-requests/?project_id=42&page=2' });
    }));
    await user.click(await screen.findByRole('tab', { name: 'Materials' }));
    expect(await screen.findByText('Latch')).toBeInTheDocument();
    expect(screen.getByText('Perch')).toBeInTheDocument();
    expect(reads).toEqual([{ project: '42', page: null }, { project: '42', page: '2' }]);
  });

  it('loads only this project and keeps quoted and progress information in the shared cards', async () => {
    const reads = [];
    const { user } = renderMaterials();
    server.use(http.get('*/api/print-requests/', ({ request }) => {
      reads.push(new URL(request.url).searchParams.get('project_id'));
      return HttpResponse.json([{ ...print, status: 'quoted', coin_cost: 3 }]);
    }));
    await user.click(await screen.findByRole('tab', { name: 'Materials' }));
    expect(await screen.findByText('Fixed quote: 3 coins')).toBeInTheDocument();
    expect(reads).toEqual(['42']);
    expect(screen.queryByRole('button', { name: /exchange 3 coins/i })).not.toBeInTheDocument();
    expect(screen.getByText(/accept coin quotes.*3D prints/i)).toBeInTheDocument();
  });

  it('lets parents track parts and prepare the printer without requesting on behalf of a child', async () => {
    const { user } = renderMaterials({ user: buildParent(), requests: [{
      ...print, status: 'approved', plate_filename: 'req-0007-perch.3mf',
    }] });
    await user.click(await screen.findByRole('tab', { name: 'Materials' }));
    expect(await screen.findByText('Perch')).toBeInTheDocument();
    expect(screen.getByText('req-0007-perch.3mf')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Request a part' })).not.toBeInTheDocument();
  });

  it('offers an explicit retry when project print tracking cannot load', async () => {
    const { user } = renderMaterials();
    let reads = 0;
    server.use(http.get('*/api/print-requests/', () => {
      reads += 1;
      return reads === 1
        ? HttpResponse.json({ detail: 'Prints are unavailable.' }, { status: 503 })
        : HttpResponse.json([print]);
    }));
    await user.click(await screen.findByRole('tab', { name: 'Materials' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Prints are unavailable.');
    await user.click(screen.getByRole('button', { name: 'Retry project prints' }));
    expect(await screen.findByText('Perch')).toBeInTheDocument();
    expect(reads).toBe(2);
  });

  it('clears the project and open request draft when the account changes', async () => {
    const { user } = renderMaterials({ requests: [print] });
    await user.click(await screen.findByRole('tab', { name: 'Materials' }));
    await user.click(await screen.findByRole('button', { name: 'Request a part' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    act(() => setToken('replacement-account'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText('Perch')).not.toBeInTheDocument();
  });
});
