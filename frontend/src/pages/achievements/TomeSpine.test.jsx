import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import TomeSpine from './TomeSpine';

const category = { id: 7, name: 'Woodworking', icon: '🪵' };

describe('TomeSpine', () => {
  it('renders as a tab with an aria-label composed from the category name', () => {
    renderWithProviders(<TomeSpine category={category} active={false} onClick={() => {}} />);
    const tab = screen.getByRole('tab');
    expect(tab).toHaveAttribute('aria-label', 'Woodworking');
  });

  it('extends the aria-label with level + XP when a summary is provided', () => {
    renderWithProviders(
      <TomeSpine
        category={category}
        active={false}
        onClick={() => {}}
        summary={{ level: 4, total_xp: 1200 }}
      />,
    );
    const tab = screen.getByRole('tab');
    expect(tab).toHaveAttribute('aria-label', 'Woodworking, level 4, 1,200 XP');
  });

  it('declares itself as the selected tab when active', () => {
    renderWithProviders(<TomeSpine category={category} active onClick={() => {}} />);
    expect(screen.getByRole('tab')).toHaveAttribute('aria-selected', 'true');
  });

  it('declares itself unselected when inactive', () => {
    renderWithProviders(<TomeSpine category={category} active={false} onClick={() => {}} />);
    expect(screen.getByRole('tab')).toHaveAttribute('aria-selected', 'false');
  });

  it('fires onClick when tapped', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(<TomeSpine category={category} active={false} onClick={spy} />);
    await user.click(screen.getByRole('tab'));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('renders the gilt foot band', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        category={category}
        active
        onClick={() => {}}
        summary={{ level: 3, total_xp: 800 }}
      />,
    );
    expect(container.querySelector('[data-tome-band="true"]')).not.toBeNull();
  });

  it('scales the bookmark ribbon up only when the tome is active', () => {
    const { container, rerender } = renderWithProviders(
      <TomeSpine category={category} active={false} onClick={() => {}} />,
    );
    let ribbon = container.querySelector('[data-tome-ribbon="true"]');
    expect(ribbon.className).toMatch(/scale-y-0/);
    rerender(<TomeSpine category={category} active onClick={() => {}} />);
    ribbon = container.querySelector('[data-tome-ribbon="true"]');
    expect(ribbon.className).toMatch(/scale-y-100/);
  });

  it('renders a level chip when a summary is provided', () => {
    renderWithProviders(
      <TomeSpine
        category={category}
        active
        onClick={() => {}}
        summary={{ level: 4 }}
      />,
    );
    expect(screen.getByText(/L ?4/)).toBeInTheDocument();
  });

  it('keeps the L# chip grouped with the foot band inside the flex tree so a long title can never overlap it', () => {
    // Collision-proof layout pin: the chip + band share a parent `<span>`
    // that sits AFTER the vertical title in DOM order. If a future refactor
    // re-absolute-positions the chip, this test fails and we catch the
    // regression before a long category name like "Woodworking" can clip
    // into the chip zone.
    const { container } = renderWithProviders(
      <TomeSpine
        category={{ id: 1, name: 'Woodworking', icon: '🪵' }}
        active
        onClick={() => {}}
        summary={{ level: 3, total_xp: 800 }}
      />,
    );
    const band = container.querySelector('[data-tome-band="true"]');
    expect(band).not.toBeNull();
    // Find the leaf span (no children) whose text is exactly "L3" — this
    // excludes the bottom-group wrapper whose concatenated textContent
    // also reads "L3" (the band has no visible text of its own).
    const chip = [...container.querySelectorAll('span')].find(
      (s) => s.children.length === 0 && /^L\d+$/.test(s.textContent.trim()),
    );
    expect(chip).not.toBeNull();
    // Chip and band live in the same immediate parent (the bottom group).
    expect(chip.parentElement).toBe(band.parentElement);
    // Neither the chip nor its parent group carries an absolute-position
    // class — they flow in the flex column so a long title can't overlap.
    expect(chip.className).not.toMatch(/\babsolute\b/);
    expect(band.parentElement.className).not.toMatch(/\babsolute\b/);
  });
});
