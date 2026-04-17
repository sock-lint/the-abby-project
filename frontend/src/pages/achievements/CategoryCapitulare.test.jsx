import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import CategoryCapitulare from './CategoryCapitulare';

const tree = {
  category: { id: 1, name: 'Woodworking', icon: '🪵' },
  summary: { level: 4, total_xp: 2850 },
  subjects: [
    {
      skills: [
        { unlocked: true, xp_points: 100 },
        { unlocked: true, xp_points: 0 },
        { unlocked: false, xp_points: 0 },
      ],
    },
    {
      skills: [{ unlocked: true, xp_points: 200 }, { unlocked: false, xp_points: 0 }],
    },
  ],
};

describe('CategoryCapitulare', () => {
  it('renders the category title + icon', () => {
    renderWithProviders(<CategoryCapitulare tree={tree} />);
    expect(screen.getByText('🪵')).toBeInTheDocument();
    expect(screen.getByText(/Woodworking/)).toBeInTheDocument();
  });

  it('shows the category level + total xp', () => {
    renderWithProviders(<CategoryCapitulare tree={tree} />);
    expect(screen.getByText(/L ?4/)).toBeInTheDocument();
    expect(screen.getByText(/2,?850\s*XP/i)).toBeInTheDocument();
  });

  it('shows the illuminated-of-total skill count from subjects', () => {
    renderWithProviders(<CategoryCapitulare tree={tree} />);
    expect(screen.getByText(/2\s*of\s*5/i)).toBeInTheDocument();
    expect(screen.getByText(/illuminated/i)).toBeInTheDocument();
  });

  it('renders a progressbar for category XP', () => {
    renderWithProviders(<CategoryCapitulare tree={tree} />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });
});
