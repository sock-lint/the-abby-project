import { describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SpriteGenerateModal from './SpriteGenerateModal.jsx';
import { renderWithProviders } from '../../test/render.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

describe('SpriteGenerateModal', () => {
  it('renders create form with slug input enabled', () => {
    const { getByLabelText } = renderWithProviders(
      <SpriteGenerateModal onClose={() => {}} />,
    );
    const slugInput = getByLabelText(/slug/i);
    expect(slugInput).not.toBeDisabled();
    expect(slugInput.value).toBe('');
  });

  it('replace mode pre-fills slug + disables it', () => {
    const sprite = {
      slug: 'fox-idle',
      prompt: 'a red fox',
      motion: 'idle',
      frame_count: 1,
      fps: 0,
      pack: 'ai-generated',
      style_hint: '',
      tile_size: 64,
      reference_image_url: '',
    };
    const { getByLabelText, getByDisplayValue } = renderWithProviders(
      <SpriteGenerateModal sprite={sprite} mode="replace" onClose={() => {}} />,
    );
    const slugInput = getByLabelText(/slug/i);
    expect(slugInput).toBeDisabled();
    expect(slugInput.value).toBe('fox-idle');
    expect(getByDisplayValue('a red fox')).toBeInTheDocument();
  });

  it('submits with the right body on create', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/sprites\/admin\/generate\/$/, {
      slug: 'newt', frame_count: 1, frame_width_px: 64, frame_height_px: 64, fps: 0,
    });
    server.use(spy.handler);

    const { getByLabelText, getByRole } = renderWithProviders(
      <SpriteGenerateModal onClose={() => {}} />,
    );
    await user.type(getByLabelText(/slug/i), 'newt');
    await user.type(getByLabelText(/prompt/i), 'pixel-art newt');
    await user.click(getByRole('button', { name: /create sprite/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toMatchObject({
      slug: 'newt',
      prompt: 'pixel-art newt',
      overwrite: false,
      motion: 'idle',
      frame_count: 1,
    });
  });

  it('submits with overwrite=true in replace mode', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/sprites\/admin\/generate\/$/, {
      slug: 'fox-idle', frame_count: 1, frame_width_px: 64, frame_height_px: 64, fps: 0,
    });
    server.use(spy.handler);

    const sprite = {
      slug: 'fox-idle',
      prompt: 'a red fox',
      motion: 'idle',
      frame_count: 1,
      fps: 0,
      pack: 'ai-generated',
      tile_size: 64,
    };
    const onSuccess = vi.fn();
    const { getByRole } = renderWithProviders(
      <SpriteGenerateModal
        sprite={sprite}
        mode="replace"
        onClose={() => {}}
        onSuccess={onSuccess}
      />,
    );
    await user.click(getByRole('button', { name: /replace sprite/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toMatchObject({
      slug: 'fox-idle',
      prompt: 'a red fox',
      overwrite: true,
    });
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });
});
