import { describe, it, expect, vi } from 'vitest';
import { useLocation } from 'react-router-dom';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import LorebookCodex from './LorebookCodex';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

// renderWithProviders mounts a MemoryRouter, so window.location never moves —
// asserting on it would pass no matter what the component did. This probe
// reads the router's own location instead.
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
}

// The deep link only opens a trial that is unlocked and not yet trained.
const entry = (over = {}) => ({
  slug: 'coins',
  title: 'Coins',
  chapter: 'economy',
  body: 'How coins work.',
  unlocked: true,
  trained: false,
  ...over,
});

function renderCodex(entries, search) {
  return renderWithProviders(
    <>
      <LorebookCodex entries={entries} mode="kid" onTrained={() => {}} />
      <LocationProbe />
    </>,
    { route: `/lorebook${search}` },
  );
}

const searchNow = () => screen.getByTestId('search').textContent;

describe('LorebookCodex — ?trial deep link', () => {
  it('opens the trial named by the param', async () => {
    renderCodex([entry()], '?trial=coins');
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('strips the param so a refresh does not re-open the trial', async () => {
    renderCodex([entry()], '?trial=coins');
    await waitFor(() => expect(searchNow()).not.toContain('trial='));
  });

  it('ignores a slug that matches no entry, and still strips the param', async () => {
    renderCodex([entry()], '?trial=nonsense');
    await waitFor(() => expect(searchNow()).not.toContain('trial='));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('leaves an already-trained entry closed', async () => {
    renderCodex([entry({ trained: true })], '?trial=coins');
    await waitFor(() => expect(searchNow()).not.toContain('trial='));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('leaves a locked entry closed', async () => {
    renderCodex([entry({ unlocked: false })], '?trial=coins');
    await waitFor(() => expect(searchNow()).not.toContain('trial='));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps other query params while stripping only trial', async () => {
    renderCodex([entry()], '?trial=coins&tab=parent');
    await waitFor(() => expect(searchNow()).not.toContain('trial='));
    expect(searchNow()).toContain('tab=parent');
  });

  it('opens nothing when no trial param is present', () => {
    renderCodex([entry()], '');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(searchNow()).toBe('');
  });
});
