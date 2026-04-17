import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SkillStanza from './SkillStanza';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function buildSkill(over = {}) {
  return {
    id: 42,
    name: 'Tape Measure',
    icon: '📏',
    description: 'Read measurements accurately',
    unlocked: true,
    is_locked_by_default: false,
    level: 2,
    level_names: { 1: 'Novice', 2: 'Journeyman', 3: 'Adept', 4: 'Master' },
    xp_points: 400,
    prerequisites: [],
    ...over,
  };
}

describe('SkillStanza', () => {
  it('renders an unlocked skill with its icon, name, and current level name', () => {
    renderWithProviders(<SkillStanza skill={buildSkill()} index={0} onSelect={() => {}} />);
    expect(screen.getByText('📏')).toBeInTheDocument();
    expect(screen.getByText('Tape Measure')).toBeInTheDocument();
    expect(screen.getByText(/Journeyman/)).toBeInTheDocument();
    expect(screen.getByText('L2')).toBeInTheDocument();
  });

  it('renders a progressbar for unlocked skills', () => {
    renderWithProviders(<SkillStanza skill={buildSkill()} index={0} onSelect={() => {}} />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('does not render a progressbar for locked skills', () => {
    renderWithProviders(
      <SkillStanza
        skill={buildSkill({ unlocked: false, is_locked_by_default: true, level: 0, xp_points: 0 })}
        index={0}
        onSelect={() => {}}
      />,
    );
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.getByText(/Locked/i)).toBeInTheDocument();
  });

  it('renders the prereq chain only when prerequisites exist', () => {
    const { container, rerender } = renderWithProviders(
      <SkillStanza skill={buildSkill()} index={0} onSelect={() => {}} />,
    );
    expect(container.querySelectorAll('[data-prereq-link="true"]').length).toBe(0);
    rerender(
      <SkillStanza
        skill={buildSkill({
          prerequisites: [{ skill_id: 9, skill_name: 'Reading Plans', required_level: 2, met: true }],
        })}
        index={0}
        onSelect={() => {}}
      />,
    );
    expect(container.querySelectorAll('[data-prereq-link="true"]').length).toBe(1);
  });

  it('shows a gilded accent for a maxed (L6) skill', () => {
    const { container } = renderWithProviders(
      <SkillStanza
        skill={buildSkill({ level: 6, xp_points: 3000 })}
        index={0}
        onSelect={() => {}}
      />,
    );
    const accent = container.querySelector('[data-accent-bar="true"]');
    expect(accent).not.toBeNull();
    expect(accent.className).toContain('bg-gold-leaf');
  });

  it('shows the locked accent for a locked skill', () => {
    const { container } = renderWithProviders(
      <SkillStanza
        skill={buildSkill({ unlocked: false, level: 0, xp_points: 0 })}
        index={0}
        onSelect={() => {}}
      />,
    );
    const accent = container.querySelector('[data-accent-bar="true"]');
    expect(accent.className).toContain('bg-ink-page-shadow');
  });

  it('fires onSelect with the skill on click', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const skill = buildSkill();
    renderWithProviders(<SkillStanza skill={skill} index={0} onSelect={spy} />);
    await user.click(screen.getByRole('button', { name: /Tape Measure/ }));
    expect(spy).toHaveBeenCalledWith(skill);
  });
});
