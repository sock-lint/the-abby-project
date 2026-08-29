import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import QuestTile from './QuestTile.jsx';

// Quest definitions have no factories.js builder; the sibling QuestCodex
// suite defines its own the same way.
const definition = (overrides = {}) => ({
  id: 7,
  name: 'Slay Beast',
  description: 'knock the beast down to zero',
  icon: '🐲',
  sprite_key: '',
  quest_type: 'boss',
  quest_type_display: 'Boss Fight',
  target_value: 100,
  duration_days: 7,
  coin_reward: 50,
  xp_reward: 100,
  required_badge: null,
  ...overrides,
});

describe('QuestTile', () => {
  it('opens the detail from a whole-card tap on an available tile', async () => {
    const onSelect = vi.fn();
    const { user } = renderWithProviders(
      <QuestTile
        quest={definition()}
        chapter="available"
        canBegin
        onBegin={vi.fn()}
        onSelect={onSelect}
      />,
    );

    // The sprite, description and meta rows used to be dead — only the name
    // text opened the sheet, while sibling tiles in the same grid were
    // whole-card buttons. The overlay now spans the card.
    const card = await screen.findByRole('button', { name: /open slay beast/i });
    expect(card.className).toMatch(/absolute inset-0/);

    await user.click(card);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0]).toMatchObject({ id: 7, name: 'Slay Beast' });
  });

  it('keeps Begin as its own tap, separate from the card overlay', async () => {
    const onBegin = vi.fn();
    const onSelect = vi.fn();
    const { user } = renderWithProviders(
      <QuestTile
        quest={definition()}
        chapter="available"
        canBegin
        onBegin={onBegin}
        onSelect={onSelect}
      />,
    );

    await user.click(await screen.findByRole('button', { name: /^Begin$/ }));
    expect(onBegin).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('still opens the detail when the tile carries no Begin button', async () => {
    const onSelect = vi.fn();
    const { user } = renderWithProviders(
      <QuestTile
        quest={definition({ name: 'Berry Hunt' })}
        chapter="available"
        canBegin={false}
        onSelect={onSelect}
      />,
    );

    await user.click(await screen.findByRole('button', { name: /open berry hunt/i }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
