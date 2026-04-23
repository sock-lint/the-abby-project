import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SpritesBlock from './SpritesBlock.jsx';

vi.mock('../../components/rpg/RpgSprite', () => ({
  default: ({ alt }) => <span data-testid="rpg-sprite" aria-label={alt} />,
}));

const SAMPLE = [
  { slug: 'fox-idle', pack: 'ai-generated', frame_count: 1, fps: 0 },
  { slug: 'wolf-walk', pack: 'ai-generated', frame_count: 4, fps: 8 },
  { slug: 'old-apple', pack: 'default', frame_count: 1, fps: 0 },
];

describe('SpritesBlock', () => {
  it('renders empty state when the catalog is empty', () => {
    render(<SpritesBlock sprites={[]} onSelect={vi.fn()} onCreate={vi.fn()} />);
    expect(screen.getByText(/no sprites registered/i)).toBeInTheDocument();
  });

  it('fires onCreate when the Create sprite button is clicked', async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    render(<SpritesBlock sprites={SAMPLE} onSelect={vi.fn()} onCreate={onCreate} />);
    await user.click(screen.getByRole('button', { name: /create sprite/i }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it('groups sprites by pack and shows every slug', () => {
    render(<SpritesBlock sprites={SAMPLE} onSelect={vi.fn()} onCreate={vi.fn()} />);
    expect(screen.getByText('fox-idle')).toBeInTheDocument();
    expect(screen.getByText('wolf-walk')).toBeInTheDocument();
    expect(screen.getByText('old-apple')).toBeInTheDocument();
    // Pack headers render
    expect(screen.getByText('ai-generated')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
  });

  it('filters by slug substring via the search box', async () => {
    const user = userEvent.setup();
    render(<SpritesBlock sprites={SAMPLE} onSelect={vi.fn()} onCreate={vi.fn()} />);

    const search = screen.getByRole('searchbox', { name: /search sprites by slug/i });
    await user.type(search, 'wolf');

    expect(screen.getByText('wolf-walk')).toBeInTheDocument();
    expect(screen.queryByText('fox-idle')).toBeNull();
    expect(screen.queryByText('old-apple')).toBeNull();
  });

  it('fires onSelect with the sprite when a tile is clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SpritesBlock sprites={SAMPLE} onSelect={onSelect} onCreate={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: /fox-idle/i }));
    expect(onSelect).toHaveBeenCalledWith(SAMPLE[0]);
  });

  it('renders animation meta on multi-frame rows and "static" on 1-frame rows', () => {
    render(<SpritesBlock sprites={SAMPLE} onSelect={vi.fn()} onCreate={vi.fn()} />);
    expect(screen.getByText('4f · 8fps')).toBeInTheDocument();
    expect(screen.getAllByText('static').length).toBeGreaterThan(0);
  });
});
