import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import TomeSpine from './TomeSpine';
import { PROGRESS_TIER } from './mastery.constants';

describe('TomeSpine', () => {
  it('renders as a tab with an aria-label defaulting to name', () => {
    renderWithProviders(
      <TomeSpine id={7} name="Woodworking" icon="🪵" active={false} onClick={() => {}} />,
    );
    expect(screen.getByRole('tab')).toHaveAttribute('aria-label', 'Woodworking');
  });

  it('honors a custom ariaLabel when one is supplied', () => {
    renderWithProviders(
      <TomeSpine
        id={7}
        name="Woodworking"
        icon="🪵"
        ariaLabel="Woodworking, level 4, 1,200 XP"
        active={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByRole('tab')).toHaveAttribute(
      'aria-label',
      'Woodworking, level 4, 1,200 XP',
    );
  });

  it('declares itself as the selected tab when active', () => {
    renderWithProviders(
      <TomeSpine id={7} name="Woodworking" icon="🪵" active onClick={() => {}} />,
    );
    expect(screen.getByRole('tab')).toHaveAttribute('aria-selected', 'true');
  });

  it('declares itself unselected when inactive', () => {
    renderWithProviders(
      <TomeSpine id={7} name="Woodworking" icon="🪵" active={false} onClick={() => {}} />,
    );
    expect(screen.getByRole('tab')).toHaveAttribute('aria-selected', 'false');
  });

  it('exposes the spine id as a data attribute', () => {
    const { container } = renderWithProviders(
      <TomeSpine id="potions" name="Potions" icon="🧪" active={false} onClick={() => {}} />,
    );
    expect(container.querySelector('[data-spine-id="potions"]')).not.toBeNull();
  });

  it('fires onClick when tapped', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TomeSpine id={7} name="Woodworking" icon="🪵" active={false} onClick={spy} />,
    );
    await user.click(screen.getByRole('tab'));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('renders the gilt foot band when progressPct is supplied', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        id={7}
        name="Woodworking"
        icon="🪵"
        active
        progressPct={42}
        tier={PROGRESS_TIER.rising}
        onClick={() => {}}
      />,
    );
    const band = container.querySelector('[data-tome-band="true"]');
    expect(band).not.toBeNull();
    expect(band.getAttribute('data-tier')).toBe('rising');
  });

  it('falls back to a thin static hairline when progressPct is null', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        id="egg"
        name="Eggs"
        icon="🥚"
        active
        progressPct={null}
        onClick={() => {}}
      />,
    );
    const band = container.querySelector('[data-tome-band="true"]');
    expect(band).not.toBeNull();
    // No filled inner bar element when progressPct is null.
    expect(band.querySelector('span')).toBeNull();
  });

  it('scales the bookmark ribbon up only when the tome is active', () => {
    const { container, rerender } = renderWithProviders(
      <TomeSpine id={7} name="Woodworking" icon="🪵" active={false} onClick={() => {}} />,
    );
    let ribbon = container.querySelector('[data-tome-ribbon="true"]');
    expect(ribbon.className).toMatch(/scale-y-0/);
    rerender(<TomeSpine id={7} name="Woodworking" icon="🪵" active onClick={() => {}} />);
    ribbon = container.querySelector('[data-tome-ribbon="true"]');
    expect(ribbon.className).toMatch(/scale-y-100/);
  });

  it('renders a chip when one is supplied', () => {
    renderWithProviders(
      <TomeSpine
        id={7}
        name="Woodworking"
        icon="🪵"
        chip="L4"
        active
        onClick={() => {}}
      />,
    );
    expect(screen.getByText('L4')).toBeInTheDocument();
  });

  it('defaults to the codex variant', () => {
    const { container } = renderWithProviders(
      <TomeSpine id={7} name="Woodworking" icon="🪵" active={false} onClick={() => {}} />,
    );
    expect(container.querySelector('[data-spine-variant="codex"]')).not.toBeNull();
    // Codex bodies have NO drawer-pull element.
    expect(container.querySelector('[data-vessel-pull="true"]')).toBeNull();
  });

  it('renders a vessel-variant body when variant="vessel"', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        id="potion"
        name="Potions"
        icon="🧪"
        variant="vessel"
        chip="×42"
        active
        onClick={() => {}}
      />,
    );
    expect(container.querySelector('[data-spine-variant="vessel"]')).not.toBeNull();
    // Vessel bodies expose the drawer-pull at the head.
    expect(container.querySelector('[data-vessel-pull="true"]')).not.toBeNull();
    // The vessel chip ('×42') is the count badge.
    expect(container.querySelector('[data-vessel-pull="true"]')).not.toBeNull();
  });

  it('keeps the chip grouped with the foot band inside the flex tree so a long title can never overlap it', () => {
    // Collision-proof layout pin: the chip + band share a parent `<span>`
    // that sits AFTER the vertical title in DOM order. If a future refactor
    // re-absolute-positions the chip, this test fails and we catch the
    // regression before a long title can clip into the chip zone.
    const { container } = renderWithProviders(
      <TomeSpine
        id={1}
        name="Woodworking"
        icon="🪵"
        chip="L3"
        progressPct={50}
        tier={PROGRESS_TIER.rising}
        active
        onClick={() => {}}
      />,
    );
    const band = container.querySelector('[data-tome-band="true"]');
    expect(band).not.toBeNull();
    const chip = [...container.querySelectorAll('span')].find(
      (s) => s.children.length === 0 && /^L\d+$/.test(s.textContent.trim()),
    );
    expect(chip).not.toBeNull();
    expect(chip.parentElement).toBe(band.parentElement);
    expect(chip.className).not.toMatch(/\babsolute\b/);
    expect(band.parentElement.className).not.toMatch(/\babsolute\b/);
  });
});
