import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import CosmeticSigil from './CosmeticSigil';

vi.mock('../../themes', async () => {
  const actual = await vi.importActual('../../themes');
  return { ...actual, applyTheme: vi.fn() };
});
import { applyTheme } from '../../themes';

const baseItem = {
  id: 1,
  name: 'Bronze Frame',
  rarity: 'common',
  icon: '\ud83d\udfeb',
  sprite_key: null,
};

beforeEach(() => {
  applyTheme.mockClear();
});

describe('CosmeticSigil', () => {
  it('renders an owned-but-not-equipped tile as a clickable button', () => {
    renderWithProviders(
      <CosmeticSigil
        entry={{ item: baseItem, owned: true, equipped: false }}
        slot="active_frame"
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    const btn = screen.getByRole('button');
    expect(btn.getAttribute('aria-label')).toMatch(/click to equip/i);
  });

  it('renders an equipped tile with the equipped ribbon', () => {
    const { container } = renderWithProviders(
      <CosmeticSigil
        entry={{ item: baseItem, owned: true, equipped: true }}
        slot="active_frame"
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    expect(
      container.querySelector('[data-cosmetic-equipped-ribbon="true"]'),
    ).not.toBeNull();
  });

  it('renders a locked tile as role=img with unlock hint, not a button', () => {
    const { container } = renderWithProviders(
      <CosmeticSigil
        entry={{ item: { ...baseItem, rarity: 'rare' }, owned: false, equipped: false }}
        slot="active_frame"
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    // Not a button
    expect(container.querySelector('button')).toBeNull();
    // Role=img with descriptive label
    const img = container.querySelector('[role="img"]');
    expect(img?.getAttribute('aria-label')).toMatch(/not yet owned/i);
    // Unlock hint present
    expect(container.querySelector('[data-cosmetic-hint="true"]')).not.toBeNull();
  });

  it('equipping fires onEquip with the item id', async () => {
    const user = userEvent.setup();
    const onEquip = vi.fn();
    renderWithProviders(
      <CosmeticSigil
        entry={{ item: baseItem, owned: true, equipped: false }}
        slot="active_frame"
        onEquip={onEquip}
        onUnequip={() => {}}
      />,
    );
    await user.click(screen.getByRole('button'));
    expect(onEquip).toHaveBeenCalledWith(1);
  });

  it('clicking an equipped tile fires onUnequip with its slot', async () => {
    const user = userEvent.setup();
    const onUnequip = vi.fn();
    renderWithProviders(
      <CosmeticSigil
        entry={{ item: baseItem, owned: true, equipped: true }}
        slot="active_frame"
        onEquip={() => {}}
        onUnequip={onUnequip}
      />,
    );
    await user.click(screen.getByRole('button'));
    expect(onUnequip).toHaveBeenCalledWith('active_frame');
  });

  it('hovering a theme tile transiently calls applyTheme; leaving restores', async () => {
    const user = userEvent.setup();
    const themeItem = {
      id: 5,
      name: 'Ocean Theme',
      rarity: 'uncommon',
      icon: '\ud83c\udf0a',
      metadata: { theme: 'ocean' },
    };
    renderWithProviders(
      <CosmeticSigil
        entry={{ item: themeItem, owned: true, equipped: false }}
        slot="active_theme"
        currentThemeName="hyrule"
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    await user.hover(screen.getByRole('button'));
    expect(applyTheme).toHaveBeenLastCalledWith('ocean');
    await user.unhover(screen.getByRole('button'));
    expect(applyTheme).toHaveBeenLastCalledWith('hyrule');
  });

  it('does not preview theme hover when the slot is not the theme slot', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <CosmeticSigil
        entry={{ item: baseItem, owned: true, equipped: false }}
        slot="active_frame"
        currentThemeName="hyrule"
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    await user.hover(screen.getByRole('button'));
    expect(applyTheme).not.toHaveBeenCalled();
  });
});
