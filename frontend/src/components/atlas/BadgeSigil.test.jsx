import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import BadgeSigil from './BadgeSigil';
import { buildBadge } from '../../test/factories';

describe('BadgeSigil', () => {
  it('renders the badge icon and name when earned', () => {
    const badge = buildBadge({ name: 'Perfect Joinery', icon: '🏆', rarity: 'rare' });
    renderWithProviders(
      <BadgeSigil badge={badge} earned earnedAt="2026-04-15T10:00:00Z" onSelect={() => {}} />,
    );
    expect(screen.getByText('🏆')).toBeInTheDocument();
    expect(screen.getByText('Perfect Joinery')).toBeInTheDocument();
  });

  it('tags earned sigils with the rarity halo class', () => {
    const badge = buildBadge({ rarity: 'legendary' });
    const { container } = renderWithProviders(
      <BadgeSigil badge={badge} earned earnedAt="2026-04-15T10:00:00Z" onSelect={() => {}} />,
    );
    const sigil = container.querySelector('[data-sigil="true"]');
    expect(sigil).not.toBeNull();
    expect(sigil.getAttribute('data-earned')).toBe('true');
    expect(sigil.getAttribute('data-rarity')).toBe('legendary');
    expect(sigil.className).toMatch(/ring-gold-leaf/);
  });

  it('keeps unearned badges identified as future goals', () => {
    const badge = buildBadge({ rarity: 'rare' });
    const { container } = renderWithProviders(
      <BadgeSigil badge={badge} earned={false} onSelect={() => {}} />,
    );
    const sigil = container.querySelector('[data-sigil="true"]');
    expect(sigil.getAttribute('data-earned')).toBe('false');
    expect(sigil.className).toMatch(/border-dashed/);
    expect(screen.getByRole('button', { name: /not yet earned/i })).toBeInTheDocument();
  });

  it('renders the unlock hint for unearned badges', () => {
    const badge = buildBadge({ name: 'Centennial', rarity: 'legendary' });
    const { container } = renderWithProviders(
      <BadgeSigil
        badge={badge}
        earned={false}
        hint="Complete 10 projects"
        onSelect={() => {}}
      />,
    );
    const hint = container.querySelector('[data-sigil-hint="true"]');
    expect(hint).not.toBeNull();
    expect(hint.textContent).toMatch(/Complete 10 projects/);
  });

  it('does not render an unlock hint on earned sigils even when one is supplied', () => {
    const badge = buildBadge();
    const { container } = renderWithProviders(
      <BadgeSigil
        badge={badge}
        earned
        earnedAt="2026-04-10"
        hint="this should not show"
        onSelect={() => {}}
      />,
    );
    expect(container.querySelector('[data-sigil-hint="true"]')).toBeNull();
  });

  it('omits the hint slot when no hint is supplied', () => {
    const badge = buildBadge();
    const { container } = renderWithProviders(
      <BadgeSigil badge={badge} earned={false} onSelect={() => {}} />,
    );
    expect(container.querySelector('[data-sigil-hint="true"]')).toBeNull();
  });

  it('renders the XP ledge on earned sigils with xp_bonus > 0', () => {
    const badge = buildBadge({ xp_bonus: 25 });
    const { container } = renderWithProviders(
      <BadgeSigil badge={badge} earned earnedAt="2026-04-15T10:00:00Z" onSelect={() => {}} />,
    );
    const xp = container.querySelector('[data-sigil-xp="true"]');
    expect(xp).not.toBeNull();
    expect(xp.textContent).toMatch(/\+25 XP/);
  });

  it('accessibly labels unearned sigils with "not yet earned"', () => {
    const badge = buildBadge({ name: 'Centennial', rarity: 'legendary' });
    renderWithProviders(<BadgeSigil badge={badge} earned={false} onSelect={() => {}} />);
    expect(
      screen.getByRole('button', { name: /Centennial.*legendary.*not yet earned/i }),
    ).toBeInTheDocument();
  });

  it('fires onSelect with the sigil payload when clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const badge = buildBadge({ id: 7 });
    renderWithProviders(
      <BadgeSigil badge={badge} earned earnedAt="2026-04-15T10:00:00Z" onSelect={spy} />,
    );
    await user.click(screen.getByRole('button'));
    expect(spy).toHaveBeenCalledWith({
      badge,
      earned: true,
      earnedAt: '2026-04-15T10:00:00Z',
    });
  });

  it('adds the gilded-glint animation class for recently-earned badges', () => {
    const badge = buildBadge({ rarity: 'rare' });
    const recent = new Date().toISOString();
    const { container } = renderWithProviders(
      <BadgeSigil badge={badge} earned earnedAt={recent} onSelect={() => {}} />,
    );
    const sigil = container.querySelector('[data-sigil="true"]');
    expect(sigil.className).toContain('animate-gilded-glint');
  });

  it('keeps a long badge name identified and selectable without a featured gold frame', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const badge = buildBadge({ name: 'AnExtraordinarilyLongUnbrokenAchievementNameThatMustRemainReadable', icon: '🦉', rarity: 'rare' });
    const { container } = renderWithProviders(<BadgeSigil badge={badge} earned onSelect={onSelect} />);
    expect(screen.getByText(badge.name)).toBeInTheDocument();
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image="frame-gold"]')).toBeNull();
    expect(screen.getByRole('button', { name: `${badge.name} · rare` })).not.toHaveAttribute('aria-pressed');
    await user.tab();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledWith({ badge, earned: true, earnedAt: null });
  });
});
