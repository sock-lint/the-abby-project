import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../test/render.jsx';
import Lorebook from './Lorebook.jsx';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return {
    ...a,
    AnimatePresence: ({ children }) => children,
    motion: {
      ...a.motion,
      li: ({ children }) => <li>{children}</li>,
      div: ({ children, ...props }) => <div {...props}>{children}</div>,
      button: ({ children, ...props }) => <button {...props}>{children}</button>,
    },
  };
});

const baseEntry = (slug, overrides = {}) => ({
  slug,
  title: slug.charAt(0).toUpperCase() + slug.slice(1),
  icon: '📖',
  chapter: 'daily_life',
  audience_title: `The ${slug} desk`,
  summary: `${slug} summary`,
  kid_voice: `${slug} kid voice`,
  mechanics: ['mechanic line'],
  parent_knobs: {},
  economy: {},
  trial_template: 'tap_and_reward',
  trial: { prompt: `tap to learn ${slug}`, payoff: '+5 XP' },
  unlocked: false,
  trained: false,
  ...overrides,
});

const buildResponse = (entries) => ({
  entries,
  counts: {
    unlocked: entries.filter((e) => e.unlocked).length,
    trained: entries.filter((e) => e.trained).length,
    total: entries.length,
  },
});

describe('Lorebook tile state machine', () => {
  it('renders locked tiles as inert intaglios', async () => {
    const entries = [baseEntry('study', { unlocked: false, trained: false })];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    renderWithProviders(<Lorebook />);

    expect(
      await screen.findByRole('img', { name: /study · not yet discovered/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /study/i })).not.toBeInTheDocument();
  });

  it('renders encountered (unlocked, untrained) tiles as Train buttons', async () => {
    const entries = [baseEntry('study', { unlocked: true, trained: false })];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    renderWithProviders(<Lorebook />);

    expect(
      await screen.findByRole('button', { name: /study · ready to train/i }),
    ).toBeInTheDocument();
  });

  it('renders inked tiles with the discovered/inked label', async () => {
    const entries = [baseEntry('study', { unlocked: true, trained: true })];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    renderWithProviders(<Lorebook />);

    expect(
      await screen.findByRole('button', { name: /study · inked/i }),
    ).toBeInTheDocument();
  });
});

describe('Lorebook trial flow', () => {
  it('opens the trial sheet on encountered tile click', async () => {
    const entries = [baseEntry('study', { unlocked: true, trained: false })];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    const { user } = renderWithProviders(<Lorebook />);

    await user.click(
      await screen.findByRole('button', { name: /study · ready to train/i }),
    );
    expect(
      await screen.findByRole('dialog', { name: /trial · study/i }),
    ).toBeInTheDocument();
  });

  it('PATCHes lorebook_flags with <slug>_trained when Ink the page is tapped', async () => {
    const entries = [baseEntry('study', { unlocked: true, trained: false })];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    const trainedEntry = { ...entries[0], trained: true };
    const patchSpy = spyHandler('patch', /\/api\/auth\/me\/$/, {
      id: 1,
      role: 'child',
      lorebook_flags: { study_trained: true },
    });
    server.use(patchSpy.handler);
    const { user } = renderWithProviders(<Lorebook />);

    await user.click(
      await screen.findByRole('button', { name: /study · ready to train/i }),
    );

    // Run the trial: tap_and_reward exposes either the target button or the
    // "I get it" ghost button. Either readies the page.
    const ghost = await screen.findByRole('button', { name: /i get it/i });
    await user.click(ghost);

    // Now Ink the page should be enabled.
    server.use(
      http.get('*/api/lorebook/', () =>
        HttpResponse.json(buildResponse([trainedEntry])),
      ),
    );
    const ink = screen.getByRole('button', { name: /ink the page/i });
    await user.click(ink);

    await waitFor(() => expect(patchSpy.calls).toHaveLength(1));
    expect(patchSpy.calls[0].body).toEqual({
      lorebook_flags: { study_trained: true },
    });
  });

  it('opens the trial sheet automatically when ?trial=<slug> is present', async () => {
    const entries = [baseEntry('study', { unlocked: true, trained: false })];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    renderWithProviders(<Lorebook />, { route: '/atlas?trial=study' });

    expect(
      await screen.findByRole('dialog', { name: /trial · study/i }),
    ).toBeInTheDocument();
  });
});

describe('Lorebook detail view (kept for trained entries)', () => {
  it('opens the existing detail sheet when an inked tile is clicked', async () => {
    const entries = [
      baseEntry('study', {
        unlocked: true,
        trained: true,
        mechanics: ['Homework pays no money and no Coins.'],
      }),
    ];
    server.use(
      http.get('*/api/lorebook/', () => HttpResponse.json(buildResponse(entries))),
    );
    const { user } = renderWithProviders(<Lorebook />);

    await user.click(await screen.findByRole('button', { name: /study · inked/i }));
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /study/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/homework pays no money/i)).toBeInTheDocument();
  });
});
