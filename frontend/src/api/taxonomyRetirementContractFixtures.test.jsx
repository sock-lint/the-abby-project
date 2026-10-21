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
import { getAllSkills, getSkillTree } from './index';
import { server } from '../test/server';
import SkillTagEditor from '../components/SkillTagEditor';
import ManagePanel from '../pages/achievements/ManagePanel';
import WayfinderSkillDetail from '../pages/achievements/WayfinderSkillDetail';

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
