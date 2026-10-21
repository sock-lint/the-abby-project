import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import active from '../../../contracts/api/fixtures/taxonomy-skills-active.json';
import management from '../../../contracts/api/fixtures/taxonomy-skills-retired-management.json';
import retired from '../../../contracts/api/fixtures/taxonomy-category-retired.json';
import restored from '../../../contracts/api/fixtures/taxonomy-category-restored.json';
import history from '../../../contracts/api/fixtures/taxonomy-tree-retired-history.json';
import staffLogin from '../../../contracts/api/fixtures/auth-login-staff-parent.json';
import staffMe from '../../../contracts/api/fixtures/auth-me-staff-parent.json';
import parentMe from '../../../contracts/api/fixtures/auth-me-ordinary-parent.json';
import childMe from '../../../contracts/api/fixtures/auth-me-child.json';
import { getAllSkills, getSkillTree } from './index';
import { server } from '../test/server';
import SkillTagEditor from '../components/SkillTagEditor';
import ManagePanel from '../pages/achievements/ManagePanel';
import WayfinderSkillDetail from '../pages/achievements/WayfinderSkillDetail';
import Achievements from '../pages/Achievements';
import Login from '../pages/Login';
import { useAuth } from '../hooks/useApi';
import { renderWithProviders } from '../test/render';
import { spyHandler } from '../test/spy';

describe('taxonomy retirement through the React client', () => {
  it('separates new skill choices from retained management identities and keeps saved XP readable', async () => {
    server.use(
      http.get('*/api/skills/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.get('include_retired') === 'true' ? management : active)),
      http.get('*/api/skills/tree/951/', () => HttpResponse.json(history)),
    );
    expect(await getAllSkills()).toEqual(active.results);
    const skills = await getAllSkills({ includeRetired: true });
    expect(skills).toEqual(management.results);
    const onChange = vi.fn();
    render(<SkillTagEditor skills={skills} value={[{ skill_id: 953, xp_weight: 3 }]} onChange={onChange} />);
    expect(screen.getByRole('combobox', { name: 'Skill for tag 1' })).toHaveTextContent('Saved skill · Unavailable for new choices (category or subject retired)');
    await userEvent.setup().click(screen.getByRole('button', { name: /add skill/i }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith([{ skill_id: 953, xp_weight: 3 }, { skill_id: 955, xp_weight: 1 }]);
    const saved = await getSkillTree(951);
    expect(saved).toEqual(history);
    expect(saved.subjects[0].skills[0]).toMatchObject({ id: 953, xp_points: 75, level: 1, unlocked: true });
    render(<WayfinderSkillDetail skill={saved.subjects[0].skills[0]} />);
    expect(screen.getByText(/75 XP/)).toBeInTheDocument();
    expect(screen.getByText('Unavailable for new choices (category or subject retired)')).toBeInTheDocument();
  });

  it('restores and retires the exact category using real PATCH responses without deleting it', async () => {
    const user = userEvent.setup();
    let current = retired;
    const patches = [];
    const deletes = vi.fn();
    server.use(
      http.get('*/api/skills/', () => HttpResponse.json(management)),
      http.get('*/api/subjects/', () => HttpResponse.json([])),
      http.get('*/api/badges/', () => HttpResponse.json([])),
      http.patch('*/api/categories/951/', async ({ request }) => {
        const body = await request.json(); patches.push(body);
        current = body.is_retired ? retired : restored;
        return HttpResponse.json(current);
      }),
      http.delete('*/api/categories/951/', () => { deletes(); return new HttpResponse(null, { status: 204 }); }),
    );
    function Management() {
      const [categories, setCategories] = useState([current]);
      return <ManagePanel categories={categories} reloadCategories={() => setCategories([current])} canManageTaxonomy />;
    }
    render(<Management />);
    await user.click(screen.getByRole('checkbox', { name: 'Show retired taxonomy' }));
    await user.click(screen.getByRole('button', { name: 'Restore category Retained practice' }));
    const retireButton = await screen.findByRole('button', { name: 'Retire category Retained practice' });
    await waitFor(() => expect(retireButton).toBeEnabled());
    await user.click(retireButton);
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Retire', exact: true }));
    await waitFor(() => expect(patches).toEqual([{ is_retired: false }, { is_retired: true }]));
    expect(await screen.findByRole('button', { name: 'Restore category Retained practice' })).toBeInTheDocument();
    expect(deletes).not.toHaveBeenCalled();
  });
});


function AuthenticatedSkills() {
  const { user, loading, login } = useAuth();
  if (loading) return null;
  return user ? <Achievements /> : <Login onLogin={login} />;
}

function renderAuthenticatedSkills(identity, { passwordLogin = false } = {}) {
  if (passwordLogin) localStorage.clear();
  let current = restored;
  const login = spyHandler('post', /\/api\/auth\/$/, staffLogin);
  const mutation = spyHandler('patch', /\/api\/categories\/951\/$/, ({ body }) => {
    current = body.is_retired ? retired : restored;
    return current;
  });
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(identity)),
    http.get('*/api/auth/google/config/', () => HttpResponse.json({ configured: false })),
    http.get('*/api/categories/', () => HttpResponse.json([current])),
    http.get('*/api/subjects/', () => HttpResponse.json([])),
    http.get('*/api/skills/', () => HttpResponse.json([])),
    http.get('*/api/badges/', () => HttpResponse.json([])),
    login.handler,
    mutation.handler,
  );
  return { ...renderWithProviders(<AuthenticatedSkills />), login, mutation };
}

describe('authenticated taxonomy retirement capability', () => {
  it.each(['verified identity', 'password login'])('lets staff retire and restore from the real %s response', async (source) => {
    const passwordLogin = source === 'password login';
    const { user, login, mutation } = renderAuthenticatedSkills(staffMe, { passwordLogin });
    if (passwordLogin) {
      await user.type(await screen.findByRole('textbox', { name: 'Username' }), staffLogin.username);
      await user.type(screen.getByLabelText('Password', { exact: true }), 'synthetic-password');
      await user.click(screen.getByRole('button', { name: 'Sign in', exact: true }));
      await waitFor(() => expect(login.calls).toHaveLength(1));
      expect(login.calls[0].body).toEqual({ action: 'login', username: staffLogin.username, password: 'synthetic-password' });
    }
    await user.click(await screen.findByRole('tab', { name: 'Manage' }));
    await user.click(screen.getByRole('checkbox', { name: 'Show retired taxonomy' }));
    await user.click(await screen.findByRole('button', { name: 'Retire category Retained practice' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Retire', exact: true }));
    const restore = await screen.findByRole('button', { name: 'Restore category Retained practice' });
    await waitFor(() => expect(restore).toBeEnabled());
    await user.click(restore);
    await waitFor(() => expect(mutation.calls).toHaveLength(2));
    expect(mutation.calls.map((call) => call.body)).toEqual([{ is_retired: true }, { is_retired: false }]);
    for (const call of mutation.calls) expect(call.url).toMatch(/\/api\/categories\/951\/$/);
    expect(await screen.findByRole('button', { name: 'Retire category Retained practice' })).toBeInTheDocument();
  });

  it('keeps retirement unavailable to the real ordinary-parent identity', async () => {
    const { user, mutation } = renderAuthenticatedSkills(parentMe);
    await user.click(await screen.findByRole('tab', { name: 'Manage' }));
    expect(await screen.findByRole('button', { name: 'Edit category Retained practice' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Retire|Restore) category/ })).not.toBeInTheDocument();
    expect(mutation.calls).toHaveLength(0);
  });

  it('keeps management unavailable to the real child identity', async () => {
    const { mutation } = renderAuthenticatedSkills(childMe);
    expect(await screen.findByRole('heading', { name: 'Skills' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Manage' })).not.toBeInTheDocument();
    expect(mutation.calls).toHaveLength(0);
  });
});
