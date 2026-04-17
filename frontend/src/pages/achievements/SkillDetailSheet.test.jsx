import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, within } from '../../test/render';
import SkillDetailSheet from './SkillDetailSheet';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function buildSkill(over = {}) {
  return {
    id: 42,
    name: 'Tape Measure',
    icon: '📏',
    description: 'Read measurements accurately.',
    unlocked: true,
    level: 2,
    level_names: { 1: 'Novice', 2: 'Journeyman', 3: 'Adept', 4: 'Master' },
    xp_points: 400,
    prerequisites: [],
    ...over,
  };
}

describe('SkillDetailSheet', () => {
  it('renders inside a dialog labeled by the skill name', () => {
    renderWithProviders(<SkillDetailSheet skill={buildSkill()} onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'Tape Measure' })).toBeInTheDocument();
  });

  it('shows the hero icon and description', () => {
    renderWithProviders(<SkillDetailSheet skill={buildSkill()} onClose={() => {}} />);
    expect(screen.getByText('📏')).toBeInTheDocument();
    expect(screen.getByText(/Read measurements accurately/)).toBeInTheDocument();
  });

  it('marks reached levels and outlines unreached levels in the roadmap', () => {
    const { baseElement } = renderWithProviders(
      <SkillDetailSheet skill={buildSkill({ level: 2 })} onClose={() => {}} />,
    );
    const roadmap = within(baseElement).getByLabelText(/Level roadmap/i);
    const reached = roadmap.querySelectorAll('[data-reached="true"]');
    const unreached = roadmap.querySelectorAll('[data-reached="false"]');
    expect(reached.length).toBe(2); // L1, L2
    expect(unreached.length).toBe(2); // L3, L4
  });

  it('renders the prereq chain when prerequisites are present', () => {
    const { baseElement } = renderWithProviders(
      <SkillDetailSheet
        skill={buildSkill({
          prerequisites: [{ skill_id: 9, skill_name: 'Reading Plans', required_level: 2, met: true }],
        })}
        onClose={() => {}}
      />,
    );
    expect(baseElement.querySelectorAll('[data-prereq-link="true"]').length).toBe(1);
  });

  it('shows a locked hint when the skill is locked', () => {
    renderWithProviders(
      <SkillDetailSheet
        skill={buildSkill({ unlocked: false, level: 0, xp_points: 0 })}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/locked/i)).toBeInTheDocument();
  });
});
