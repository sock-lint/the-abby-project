import { selectDropdown, openDropdown } from '../../test/selectDropdown';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, within } from '../../test/render';
import AvatarCustomizer from './AvatarCustomizer';
import { resolveAvatarCatalog, defaultConfiguration } from '../../pages/avatar-customize/catalog';
import { syntheticCatalog } from '../../pages/avatar-customize/catalog.fixtures';
const catalog = resolveAvatarCatalog(syntheticCatalog);
const knight = catalog.avatars[1];

describe('catalog-driven shared AvatarCustomizer controls', () => {
  it('shows generic fit-bound accessories including the same Archer bows and quivers on another base', async () => {
    const user = userEvent.setup(); const onChange = vi.fn();
    renderWithProviders(<AvatarCustomizer avatarDefinition={knight} configuration={defaultConfiguration(knight)} onChange={onChange} />, { withAuth: false });
    expect(screen.getByRole('group', { name: 'Wardrobe' })).toBeInTheDocument();
    const weapon = screen.getByRole('combobox', { name: 'Weapon' });
    const weapons = await openDropdown(user, weapon);
    expect(weapons.getByRole('option', { name: 'Greenhorn bow' })).toHaveAttribute('data-value', 'bow-greenhorn');
    expect(weapons.getByRole('option', { name: 'Round shield' })).toHaveAttribute('data-value', 'shield-round');
    await selectDropdown(user, weapon, 'bow-greenhorn');
    expect(onChange).toHaveBeenCalledExactlyOnceWith({ accessories: { left_hand: 'bow-greenhorn' } });
    const backAccessories = await openDropdown(user, screen.getByRole('combobox', { name: 'Back accessory' }));
    expect(backAccessories.getByRole('option', { name: 'Rook quiver' })).toHaveAttribute('data-value', 'quiver-rook');
    expect(screen.queryByRole('combobox', { name: 'Bow' })).toBeNull();
  });
  it('uses structured preset patches, preserves unavailable saved values and disables controls while saving', async () => {
    const user = userEvent.setup(); const onChange = vi.fn();const archer = catalog.avatars[0];
    const configuration = defaultConfiguration(archer);
    const view = renderWithProviders(<AvatarCustomizer avatarDefinition={archer} configuration={configuration} onChange={onChange} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Fire' }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith({ appearance: archer.presets[0].appearance, accessories: archer.presets[0].accessories });
    const saved = { ...configuration, accessories: { ...configuration.accessories, back: 'retired-item' } };
    view.rerender(<AvatarCustomizer avatarDefinition={archer} configuration={saved} onChange={onChange} />);
    const back = screen.getByRole('combobox', { name: 'Back accessory' });
    expect(back).toHaveValue('retired-item');
    const savedChoices = await openDropdown(user, back);
    expect(savedChoices.getByRole('option', { name: 'Unavailable saved choice' })).toHaveAttribute('aria-disabled', 'true');
    view.rerender(<AvatarCustomizer avatarDefinition={archer} configuration={saved} onChange={onChange} disabled />);
    expect(screen.getByRole('button', { name: 'Fire' })).toBeDisabled();
    within(screen.getByRole('group', { name: 'Wardrobe' })).getAllByRole('combobox').forEach((select) => expect(select).toBeDisabled());
  });
});
