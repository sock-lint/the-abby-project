import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '../../test/render';
import SkillsShowcase from './SkillsShowcase';

function breadcrumb() {
  return screen.getByRole('navigation', { name: 'Skills demo breadcrumb' });
}

describe('Skills design showcase', () => {
  it('drills through production maps, rows, and detail without an account or API request', async () => {
    localStorage.clear();
    const request = vi.spyOn(globalThis, 'fetch');
    try {
      const { user } = renderWithProviders(<SkillsShowcase />, { withAuth: false });
      expect(screen.getByText(/synthetic catalog and progress examples/i)).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Your skills' })).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Woodworking, 2 subjects · 4 skills' }));
      expect(screen.getByRole('heading', { name: 'Woodworking' })).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Workshop foundations, 2 skills' }));
      expect(screen.getByRole('heading', { name: 'Workshop foundations' })).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /^Measure & Mark, level 3/ }));
      expect(screen.getByRole('heading', { name: 'Measure & Mark' })).toBeInTheDocument();
      expect(screen.getByText('Level 3 · Precise planner · 780 XP')).toBeInTheDocument();
      expect(screen.getByRole('progressbar', { name: 'Measure & Mark XP progress toward level 4' })).toHaveAttribute('aria-valuenow', '45');
      expect(breadcrumb().querySelector('[aria-current="page"]')).toHaveTextContent('Measure & Mark');
      await user.click(screen.getByRole('button', { name: 'Back' }));
      expect(screen.getByRole('heading', { name: 'Workshop foundations' })).toBeInTheDocument();
      await user.click(within(breadcrumb()).getByRole('button', { name: 'All skills' }));
      expect(screen.getByRole('heading', { name: 'Your skills' })).toBeInTheDocument();
      expect(request).not.toHaveBeenCalled();
    } finally {
      request.mockRestore();
    }
  });

  it('follows a cross-category requirement and returns to the skill that opened it', async () => {
    const { user } = renderWithProviders(<SkillsShowcase />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: /^Woodworking,/ }));
    await user.click(screen.getByRole('button', { name: 'Finishing & decorative techniques, 2 skills' }));
    await user.click(screen.getByRole('button', { name: /^Inlay Work, locked/ }));
    expect(screen.getByText('Locked — meet these skill requirements to unlock.')).toBeInTheDocument();
    const paths = within(screen.getByRole('region', { name: 'Prerequisite paths' }));
    const gilding = paths.getByRole('button', { name: /^Gilding/ });
    expect(gilding).toHaveTextContent('Art & Crafts · Requires Level 3 · Not yet met');
    await user.click(gilding);
    expect(screen.getByRole('heading', { name: 'Gilding' })).toBeInTheDocument();
    expect(breadcrumb()).toHaveTextContent('Art & Crafts');
    expect(breadcrumb()).toHaveTextContent('Surface decoration');
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('heading', { name: 'Inlay Work' })).toBeInTheDocument();
    expect(breadcrumb()).toHaveTextContent('Woodworking');
  });

  it('searches skill descriptions within a branch and clears search when navigating', async () => {
    const { user } = renderWithProviders(<SkillsShowcase />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: /^Woodworking,/ }));
    await user.type(screen.getByRole('searchbox', { name: 'Filter demo skills' }), 'accurate marks');
    expect(screen.getByRole('button', { name: /^Measure & Mark,/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Read a Plan,/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Workshop foundations,/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Measure & Mark,/ }));
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('searchbox', { name: 'Filter demo skills' })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Workshop foundations, 2 skills' })).toBeInTheDocument();
  });
});
