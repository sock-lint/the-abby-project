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

  it('declares itself a leather-bound tome with a tier data-attribute on codex variants', () => {
    // Library of Mastery — pattern-matchable selectors so any future
    // restyling without these decorations fails loud.
    const { container } = renderWithProviders(
      <TomeSpine
        id="electronics"
        name="Electronics"
        icon="⚡"
        active={false}
        progressPct={42}
        tier={PROGRESS_TIER.rising}
        onClick={() => {}}
      />,
    );
    const root = container.querySelector('[data-spine-id="electronics"]');
    expect(root).not.toBeNull();
    expect(root.getAttribute('data-binding')).toBe('leather');
    expect(root.getAttribute('data-tier')).toBe('rising');
    expect(root.className).toMatch(/spine-leather/);
  });

  it('renders the full codex dressing (headband, three binding bands, gilt edge, brass medallion, foil title)', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        id="electronics"
        name="Electronics"
        icon="⚡"
        active={false}
        tier={PROGRESS_TIER.rising}
        onClick={() => {}}
      />,
    );
    expect(container.querySelector('[data-spine-headband="true"]')).not.toBeNull();
    expect(container.querySelector('[data-spine-band="head"]')).not.toBeNull();
    expect(container.querySelector('[data-spine-band="middle"]')).not.toBeNull();
    expect(container.querySelector('[data-spine-band="foot"]')).not.toBeNull();
    expect(container.querySelector('[data-spine-edge="true"]')).not.toBeNull();
    expect(container.querySelector('[data-spine-medallion="true"]')).not.toBeNull();
    const title = container.querySelector('[data-spine-title="true"]');
    expect(title).not.toBeNull();
    expect(title.className).toMatch(/spine-foil/);
    expect(title.className).toMatch(/spine-foil-glint/);
  });

  it('reveals the page-block sliver only when active (the rotateY tilt would expose nothing otherwise)', () => {
    const { container, rerender } = renderWithProviders(
      <TomeSpine
        id="electronics"
        name="Electronics"
        icon="⚡"
        active={false}
        tier={PROGRESS_TIER.rising}
        onClick={() => {}}
      />,
    );
    expect(container.querySelector('[data-spine-pageblock="true"]')).toBeNull();
    rerender(
      <TomeSpine
        id="electronics"
        name="Electronics"
        icon="⚡"
        active
        tier={PROGRESS_TIER.rising}
        onClick={() => {}}
      />,
    );
    expect(container.querySelector('[data-spine-pageblock="true"]')).not.toBeNull();
  });

  it('codex headband tier-colors map to the PROGRESS_TIER vocabulary', () => {
    // Five tiers, five headband tints — pinned via data-tier on the band so
    // a future palette swap stays loud if it forgets one tier.
    const tiers = [
      ['locked', PROGRESS_TIER.locked],
      ['nascent', PROGRESS_TIER.nascent],
      ['rising', PROGRESS_TIER.rising],
      ['cresting', PROGRESS_TIER.cresting],
      ['gilded', PROGRESS_TIER.gilded],
    ];
    for (const [key, tier] of tiers) {
      const { container, unmount } = renderWithProviders(
        <TomeSpine
          id={`x-${key}`}
          name="Whatever"
          icon="✦"
          active={false}
          tier={tier}
          onClick={() => {}}
        />,
      );
      const band = container.querySelector('[data-spine-headband="true"]');
      expect(band, `tier ${key} should render a headband`).not.toBeNull();
      expect(band.getAttribute('data-tier')).toBe(key);
      unmount();
    }
  });

  it('vessel variants stay drawer-shaped and skip every codex dressing', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        id="potions"
        name="Potions"
        icon="🧪"
        variant="vessel"
        active
        onClick={() => {}}
      />,
    );
    const root = container.querySelector('[data-spine-id="potions"]');
    expect(root.getAttribute('data-binding')).toBe('drawer');
    expect(root.className).not.toMatch(/spine-leather/);
    expect(container.querySelector('[data-spine-headband="true"]')).toBeNull();
    expect(container.querySelector('[data-spine-band="middle"]')).toBeNull();
    expect(container.querySelector('[data-spine-edge="true"]')).toBeNull();
    expect(container.querySelector('[data-spine-medallion="true"]')).toBeNull();
    expect(container.querySelector('[data-spine-title="true"]')).toBeNull();
    // Vessel ribbon does NOT carry the cloth-curl settle animation — that
    // beat belongs to the bound codex, not the drawer pull.
    const ribbon = container.querySelector('[data-tome-ribbon="true"]');
    expect(ribbon.className).not.toMatch(/animate-ribbon-settle/);
  });

  it('active codex ribbon gets the cloth-settle keyframe so it reads as fabric falling into place', () => {
    const { container } = renderWithProviders(
      <TomeSpine
        id="electronics"
        name="Electronics"
        icon="⚡"
        active
        tier={PROGRESS_TIER.rising}
        onClick={() => {}}
      />,
    );
    const ribbon = container.querySelector('[data-tome-ribbon="true"]');
    expect(ribbon.className).toMatch(/animate-ribbon-settle/);
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
