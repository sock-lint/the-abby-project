import { describe, expect, it, vi } from 'vitest';
import { render, screen, userEvent, within } from '../../test/render';
import WayfinderSkillDetail from './WayfinderSkillDetail';

function buildSkill(overrides = {}) {
  return {
    id: 42,
    name: 'Joinery',
    icon: '🔗',
    description: 'Join wood into strong structures.',
    category_name: 'Woodworking',
    unlocked: true,
    level: 2,
    xp_points: 450,
    level_names: {
      1: 'Glue & Pray',
      2: 'Butt Joints',
      3: 'Dado & Rabbet',
      4: 'Dovetailer',
      5: 'Mortise Master',
    },
    prerequisites: [],
    ...overrides,
  };
}

function renderDetail(skill, overrides = {}) {
  const props = {
    skill,
    resolvePrerequisite: vi.fn(() => null),
    onSelectPrerequisite: vi.fn(),
    ...overrides,
  };
  return { ...render(<WayfinderSkillDetail {...props} />), ...props };
}

function expectProgressPercent(percent) {
  const progress = screen.getByRole('progressbar');
  const current = Number(progress.getAttribute('aria-valuenow'));
  const max = Number(progress.getAttribute('aria-valuemax'));
  expect(current / max * 100).toBeCloseTo(percent, 0);
}

describe('WayfinderSkillDetail', () => {
  it('shows server-confirmed level, XP and actual progress to the next level', () => {
    renderDetail(buildSkill());

    expect(screen.getByRole('heading', { level: 2, name: 'Joinery' })).toBeInTheDocument();
    expect(screen.getByText('Join wood into strong structures.')).toBeInTheDocument();
    expect(screen.getAllByText(/Butt Joints/).length).toBeGreaterThan(0);
    expect(screen.getByText(/450.*XP/i)).toBeInTheDocument();
    expect(screen.getByText(/150.*(?:Level 3|L3)/i)).toBeInTheDocument();
    // Level 2 starts at 300 XP and Level 3 at 600 XP.
    expectProgressPercent(50);
  });

  it('uses the server level rather than deriving a replacement level from XP', () => {
    renderDetail(buildSkill({ level: 1, xp_points: 450 }));

    expect(screen.getByText(/Level 1.*Glue & Pray/i)).toBeInTheDocument();
    expectProgressPercent(100);
    const roadmap = screen.getByRole('list', { name: 'Level roadmap' });
    expect(within(roadmap).getAllByRole('listitem').filter((item) => item.dataset.reached === 'true')).toHaveLength(1);
  });

  it('shows all six level destinations with catalog titles and the mastery fallback', () => {
    renderDetail(buildSkill());

    const roadmap = screen.getByRole('list', { name: 'Level roadmap' });
    const levels = within(roadmap).getAllByRole('listitem');
    expect(levels).toHaveLength(6);
    expect(levels.map((item) => item.dataset.reached)).toEqual(['true', 'true', 'false', 'false', 'false', 'false']);
    expect(levels[0]).toHaveTextContent('Glue & Pray');
    expect(levels[1]).toHaveTextContent('Butt Joints');
    expect(levels[2]).toHaveTextContent('Dado & Rabbet');
    expect(levels[3]).toHaveTextContent('Dovetailer');
    expect(levels[4]).toHaveTextContent('Mortise Master');
    expect(levels[5]).toHaveTextContent('Mastery');
  });

  it('shows mastery at the maximum server level without offering a nonexistent next level', () => {
    renderDetail(buildSkill({ level: 6, xp_points: 2750 }));

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getAllByText(/mastery/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/(?:Level 7|L7)/i)).not.toBeInTheDocument();
    const levels = within(screen.getByRole('list', { name: 'Level roadmap' })).getAllByRole('listitem');
    expect(levels.every((item) => item.dataset.reached === 'true')).toBe(true);
  });

  it('keeps a server-locked skill locked and shows requirements without an XP progress bar', () => {
    const requirement = { skill_id: 9, skill_name: 'Hand Tools', required_level: 3, met: true };
    renderDetail(buildSkill({ unlocked: false, level: 0, xp_points: 0, prerequisites: [requirement] }), {
      resolvePrerequisite: vi.fn(() => ({ categoryName: 'Woodworking' })),
    });

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getAllByText(/locked/i).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Hand Tools.*Requires Level 3.*Met/i })).toBeEnabled();
    const levels = within(screen.getByRole('list', { name: 'Level roadmap' })).getAllByRole('listitem');
    expect(levels.every((item) => item.dataset.reached === 'false')).toBe(true);
  });

  it('explains a locked skill even when the API returns no prerequisite paths', () => {
    renderDetail(buildSkill({ unlocked: false, level: 0, xp_points: 0, prerequisites: [] }));

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getAllByText(/locked|unlock/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('follows a cross-category prerequisite and reports only the server met status', async () => {
    const requirement = { skill_id: 70, skill_name: 'Logical Thinking', required_level: 2, met: false };
    const resolvePrerequisite = vi.fn(() => ({ categoryName: 'Coding' }));
    const onSelectPrerequisite = vi.fn();
    renderDetail(buildSkill({ prerequisites: [requirement] }), { resolvePrerequisite, onSelectPrerequisite });

    const path = screen.getByRole('button', { name: /Logical Thinking.*Requires Level 2.*Not yet met/i });
    expect(path).toHaveTextContent('Coding');
    expect(path).not.toHaveTextContent(/Currently Level|Current Level/i);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    await userEvent.click(path);
    expect(onSelectPrerequisite).toHaveBeenCalledExactlyOnceWith(requirement);
    expect(resolvePrerequisite).toHaveBeenCalledWith(requirement);
  });

  it('disables a prerequisite whose catalog destination is unavailable', async () => {
    const requirement = { skill_id: 404, skill_name: 'Unknown destination', required_level: 1, met: false };
    const { onSelectPrerequisite } = renderDetail(buildSkill({ prerequisites: [requirement] }));

    const path = screen.getByRole('button', { name: /Unknown destination.*Requires Level 1/i });
    expect(path).toBeDisabled();
    expect(path).toHaveTextContent(/Destination unavailable/i);
    await userEvent.click(path);
    expect(onSelectPrerequisite).not.toHaveBeenCalled();
  });

  it('keeps prerequisite navigation disabled while catalog destinations are loading', async () => {
    const requirement = { skill_id: 9, skill_name: 'Hand Tools', required_level: 3, met: true };
    const { onSelectPrerequisite } = renderDetail(buildSkill({ prerequisites: [requirement] }), { catalogLoading: true });

    const path = screen.getByRole('button', { name: /Hand Tools.*Requires Level 3/i });
    expect(path).toBeDisabled();
    expect(path).toHaveTextContent(/loading/i);
    expect(path).not.toHaveTextContent(/Destination unavailable/i);
    await userEvent.click(path);
    expect(onSelectPrerequisite).not.toHaveBeenCalled();
  });
});
