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
    expect(within(weapon).getByRole('option', { name: 'Greenhorn bow' })).toHaveValue('bow-greenhorn');
    expect(within(weapon).getByRole('option', { name: 'Round shield' })).toHaveValue('shield-round');
    await user.selectOptions(weapon, 'bow-greenhorn');
    expect(onChange).toHaveBeenCalledExactlyOnceWith({ accessories: { left_hand: 'bow-greenhorn' } });
    expect(within(screen.getByRole('combobox', { name: 'Back accessory' })).getByRole('option', { name: 'Rook quiver' })).toHaveValue('quiver-rook');
    expect(screen.queryByRole('combobox', { name: 'Bow' })).toBeNull();
  });
  it('uses structured preset patches, preserves unavailable saved values and disables controls while saving', async () => {
    const user = userEvent.setup(); const onChange = vi.fn();const archer = catalog.avatars[0];
    const configuration = defaultConfiguration(archer);
    const view = renderWithProviders(<AvatarCustomizer avatarDefinition={archer} configuration={configuration} onChange={onChange} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Fire' }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith({ appearance: archer.presets[0].appearance, accessories: archer.presets[0].accessories });
    view.rerender(<AvatarCustomizer avatarDefinition={archer} configuration={{ ...configuration, accessories: { ...configuration.accessories, back: 'retired-item' } }} onChange={onChange} disabled />);
    expect(screen.getByRole('combobox', { name: 'Back accessory' })).toHaveValue('retired-item');
    expect(screen.getByRole('option', { name: 'Unavailable saved choice' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fire' })).toBeDisabled();
    within(screen.getByRole('group', { name: 'Wardrobe' })).getAllByRole('combobox').forEach((select) => expect(select).toBeDisabled());
  });
});
