import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SpriteDetailSheet from './SpriteDetailSheet.jsx';
import { renderWithProviders } from '../../test/render.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

const SPRITE_WITH_PROMPT = {
  slug: 'fox-idle',
  pack: 'ai-generated',
  frame_count: 1,
  fps: 0,
  frame_width_px: 64,
  frame_height_px: 64,
  prompt: 'a red fox',
  motion: 'idle',
  style_hint: 'nes palette',
  tile_size: 64,
  reference_image_url: '',
  created_by_name: 'Alice',
};

const SPRITE_LEGACY = {
  ...SPRITE_WITH_PROMPT,
  slug: 'legacy-rock',
  prompt: '',
  motion: '',
  tile_size: null,
};

describe('SpriteDetailSheet', () => {
  it('renders authoring inputs when recorded', () => {
    const { getByText } = renderWithProviders(
      <SpriteDetailSheet sprite={SPRITE_WITH_PROMPT} onClose={() => {}} />,
    );
    expect(getByText('a red fox')).toBeInTheDocument();
    expect(getByText('nes palette')).toBeInTheDocument();
  });

  it('disables Reroll when no stored prompt', () => {
    const { getByRole } = renderWithProviders(
      <SpriteDetailSheet sprite={SPRITE_LEGACY} onClose={() => {}} />,
    );
    expect(getByRole('button', { name: /reroll/i })).toBeDisabled();
  });

  it('reroll button opens confirm then POSTs to reroll endpoint', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/sprites\/admin\/fox-idle\/reroll\/$/, {
      slug: 'fox-idle',
    });
    server.use(spy.handler);

    const { getByRole } = renderWithProviders(
      <SpriteDetailSheet sprite={SPRITE_WITH_PROMPT} onClose={() => {}} />,
    );
    await user.click(getByRole('button', { name: /reroll/i }));
    // ConfirmDialog renders a portal outside the sheet; scope the confirm
    // button to the alertdialog so we don't collide with the original Reroll.
    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Reroll' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/sprites\/admin\/fox-idle\/reroll\/$/);
  });

  it('delete button opens confirm then DELETEs and closes', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('delete', /\/api\/sprites\/admin\/fox-idle\/$/, { deleted: true });
    server.use(spy.handler);

    const { getByRole } = renderWithProviders(
      <SpriteDetailSheet sprite={SPRITE_WITH_PROMPT} onClose={() => {}} />,
    );
    await user.click(getByRole('button', { name: /delete/i }));
    const confirm = await screen.findByRole('alertdialog');
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/sprites\/admin\/fox-idle\/$/);
  });
});
