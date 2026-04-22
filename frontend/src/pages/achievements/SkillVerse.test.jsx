import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SkillVerse from './SkillVerse';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function buildSkill(over = {}) {
  return {
    id: 42,
    name: 'Mortise and Tenon',
    icon: '🪵',
    unlocked: true,
    level: 2,
    level_names: { 1: 'Novice', 2: 'Journeyman', 3: 'Adept', 4: 'Master' },
    xp_points: 400,
    prerequisites: [],
    ...over,
  };
}

describe('SkillVerse', () => {
  it('renders the skill name + current level name', () => {
    renderWithProviders(<SkillVerse skill={buildSkill()} index={0} onSelect={() => {}} />);
    expect(screen.getByText('Mortise and Tenon')).toBeInTheDocument();
    expect(screen.getByText(/Journeyman/)).toBeInTheDocument();
    expect(screen.getByText('L2')).toBeInTheDocument();
  });

  it('renders an illuminated versal with the first letter of the skill', () => {
    const { container } = renderWithProviders(
      <SkillVerse skill={buildSkill()} index={0} onSelect={() => {}} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).not.toBeNull();
    expect(versal.textContent).toContain('M');
  });

  it('composes a descriptive aria-label for unlocked skills', () => {
    renderWithProviders(<SkillVerse skill={buildSkill()} index={0} onSelect={() => {}} />);
    const btn = screen.getByRole('button');
    const label = btn.getAttribute('aria-label') || '';
    expect(label).toMatch(/Mortise and Tenon/);
    expect(label).toMatch(/level 2/);
    expect(label).toMatch(/Journeyman/);
  });

  it('shows the level strap progress indicator for unlocked-but-not-maxed skills', () => {
    const { container } = renderWithProviders(
      <SkillVerse skill={buildSkill()} index={0} onSelect={() => {}} />,
    );
    expect(container.querySelector('[data-level-strap="true"]')).not.toBeNull();
  });

  it('marks locked skills and renders "locked — forge prerequisites first"', () => {
    renderWithProviders(
      <SkillVerse
        skill={buildSkill({
          unlocked: false,
          level: 0,
          xp_points: 0,
          prerequisites: [{ skill_id: 9, skill_name: 'Reading Plans', required_level: 2, met: false }],
        })}
        index={0}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/locked — forge prerequisites first/i)).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveAttribute('data-locked', 'true');
  });

  it('renders the prereq chain only when prerequisites exist', () => {
    const { container, rerender } = renderWithProviders(
      <SkillVerse skill={buildSkill()} index={0} onSelect={() => {}} />,
    );
    expect(container.querySelectorAll('[data-prereq-link="true"]').length).toBe(0);
    rerender(
      <SkillVerse
        skill={buildSkill({
          prerequisites: [{ skill_id: 9, skill_name: 'Reading Plans', required_level: 2, met: true }],
        })}
        index={0}
        onSelect={() => {}}
      />,
    );
    expect(container.querySelectorAll('[data-prereq-link="true"]').length).toBe(1);
  });

  it('shows the mastery rune for maxed (L6) skills and hides the level strap', () => {
    const { container } = renderWithProviders(
      <SkillVerse skill={buildSkill({ level: 6, xp_points: 3000 })} index={0} onSelect={() => {}} />,
    );
    expect(screen.getByText(/mastery/i)).toBeInTheDocument();
    expect(container.querySelector('[data-level-strap="true"]')).toBeNull();
  });

  it('fires onSelect with the skill on click', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const skill = buildSkill();
    renderWithProviders(<SkillVerse skill={skill} index={0} onSelect={spy} />);
    await user.click(screen.getByRole('button'));
    expect(spy).toHaveBeenCalledWith(skill);
  });
});
