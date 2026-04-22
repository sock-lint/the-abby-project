import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import FolioSpread from './FolioSpread';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function buildTree(over = {}) {
  return {
    category: { id: 1, name: 'Woodworking', icon: '🪵' },
    summary: { level: 4, total_xp: 2850 },
    subjects: [
      {
        id: 10,
        name: 'Joinery',
        icon: '🔨',
        summary: { level: 3, total_xp: 1400 },
        skills: [
          {
            id: 1,
            name: 'Mortise and Tenon',
            icon: '🪵',
            level: 4,
            xp_points: 950,
            unlocked: true,
            level_names: { 4: 'Master' },
            prerequisites: [],
          },
          {
            id: 2,
            name: 'Dovetails',
            icon: '🪵',
            level: 2,
            xp_points: 250,
            unlocked: true,
            level_names: { 2: 'Journeyman' },
            prerequisites: [],
          },
        ],
      },
      {
        id: 11,
        name: 'Finishing',
        icon: '🎨',
        summary: { level: 2, total_xp: 350 },
        skills: [
          {
            id: 3,
            name: 'Shellac',
            icon: '🧴',
            level: 1,
            xp_points: 80,
            unlocked: true,
            level_names: { 1: 'Apprentice' },
            prerequisites: [],
          },
        ],
      },
    ],
    ...over,
  };
}

describe('FolioSpread', () => {
  it('renders the category name and icon in the verso hero', () => {
    renderWithProviders(<FolioSpread tree={buildTree()} onSelectSkill={() => {}} />);
    expect(screen.getByText(/Woodworking/)).toBeInTheDocument();
    expect(screen.getAllByText('🪵').length).toBeGreaterThanOrEqual(1);
  });

  it('shows category level + total XP in the verso hero', () => {
    renderWithProviders(<FolioSpread tree={buildTree()} onSelectSkill={() => {}} />);
    // "L4" appears on both the category hero and any skill at L4; assert
    // the hero-specific total XP value (2850) is present once and that at
    // least one "L4" chip exists.
    expect(screen.getAllByText(/L ?4/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/2,?850/)).toBeInTheDocument();
  });

  it('renders a category progressbar', () => {
    renderWithProviders(<FolioSpread tree={buildTree()} onSelectSkill={() => {}} />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('counts illuminated skills based on the subjects array', () => {
    renderWithProviders(<FolioSpread tree={buildTree()} onSelectSkill={() => {}} />);
    // All 3 have xp_points > 0 → "3 of 3 illuminated"
    expect(screen.getByText(/3 of 3 illuminated/i)).toBeInTheDocument();
  });

  it('renders a chapter rubric + skills for every subject', () => {
    renderWithProviders(<FolioSpread tree={buildTree()} onSelectSkill={() => {}} />);
    expect(screen.getByText('Joinery')).toBeInTheDocument();
    expect(screen.getByText('Finishing')).toBeInTheDocument();
    expect(screen.getByText('Mortise and Tenon')).toBeInTheDocument();
    expect(screen.getByText('Dovetails')).toBeInTheDocument();
    expect(screen.getByText('Shellac')).toBeInTheDocument();
    expect(screen.getByText('§I')).toBeInTheDocument();
    expect(screen.getByText('§II')).toBeInTheDocument();
  });

  it('passes the clicked skill to onSelectSkill', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(<FolioSpread tree={buildTree()} onSelectSkill={spy} />);
    await user.click(screen.getByRole('button', { name: /Mortise and Tenon/ }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0].name).toBe('Mortise and Tenon');
  });

  it('renders nothing when the tree is null', () => {
    const { container } = renderWithProviders(
      <FolioSpread tree={null} onSelectSkill={() => {}} />,
    );
    expect(container.textContent).toBe('');
  });

  it('shows an empty message when the tree has no subjects', () => {
    renderWithProviders(
      <FolioSpread
        tree={{ category: { id: 1, name: 'Empty' }, summary: { level: 0, total_xp: 0 }, subjects: [] }}
        onSelectSkill={() => {}}
      />,
    );
    expect(screen.getByText(/still blank/i)).toBeInTheDocument();
  });
});
