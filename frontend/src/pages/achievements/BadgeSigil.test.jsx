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
    // Halo uses ring on gold-leaf for legendary.
    expect(sigil.className).toMatch(/ring-gold-leaf/);
  });

  it('renders unearned badges as a debossed silhouette', () => {
    const badge = buildBadge({ rarity: 'rare' });
    const { container } = renderWithProviders(
      <BadgeSigil badge={badge} earned={false} onSelect={() => {}} />,
    );
    const sigil = container.querySelector('[data-sigil="true"]');
    expect(sigil.getAttribute('data-earned')).toBe('false');
    // Unearned uses a dashed border and suppressed ink.
    expect(sigil.className).toMatch(/border-dashed/);
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
});
