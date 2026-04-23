import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import StreakGlyph from './StreakGlyph';

describe('StreakGlyph', () => {
  it('renders the active streak with flame + label', () => {
    renderWithProviders(<StreakGlyph kind="streak" value={14} longestStreak={30} />);
    // StreakFlame renders "14 days" text + "longest: 30"
    expect(screen.getByText(/14 days/)).toBeInTheDocument();
    expect(screen.getByText(/longest:\s*30/)).toBeInTheDocument();
  });

  it('tags the streak pip with the correct tier data attribute', () => {
    const { container } = renderWithProviders(
      <StreakGlyph kind="streak" value={30} longestStreak={30} />,
    );
    const pip = container.querySelector('[data-streak-glyph="streak"]');
    expect(pip?.getAttribute('data-tier')).toBe('cresting');
  });

  it('renders the perfect-days pip with star glyph', () => {
    renderWithProviders(<StreakGlyph kind="perfect" value={12} />);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('perfect days')).toBeInTheDocument();
  });

  it('renders the best-streak pip with award glyph', () => {
    renderWithProviders(<StreakGlyph kind="best" value={47} />);
    expect(screen.getByText('47')).toBeInTheDocument();
    expect(screen.getByText('best streak')).toBeInTheDocument();
  });
});
