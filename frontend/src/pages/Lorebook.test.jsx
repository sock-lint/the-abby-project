import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Lorebook from './Lorebook.jsx';
import { server } from '../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return {
    ...a,
    AnimatePresence: ({ children }) => children,
    motion: {
      ...a.motion,
      li: ({ children }) => <li>{children}</li>,
      div: ({ children, ...props }) => <div {...props}>{children}</div>,
    },
  };
});

const entries = [
  {
    slug: 'study',
    title: 'Study',
    icon: '📚',
    chapter: 'daily_life',
    summary: 'Homework is school duty.',
    audience_title: 'The scholar desk',
    kid_voice: 'Study earns mastery.',
    mechanics: ['Homework pays no money and no Coins.'],
    parent_knobs: {},
    economy: { money: false, coins: false, xp: true },
    unlocked: true,
  },
  {
    slug: 'pets',
    title: 'Pets',
    icon: '🐾',
    chapter: 'rpg_layer',
    summary: 'Egg + potion companions.',
    kid_voice: 'Pets are companions.',
    mechanics: ['Hatch with an egg and potion.'],
    parent_knobs: {},
    economy: {},
    unlocked: false,
  },
];

describe('Lorebook', () => {
  it('renders unlocked entries as buttons and locked entries as intaglios', async () => {
    server.use(
      http.get('*/api/lorebook/', () =>
        HttpResponse.json({ entries, counts: { unlocked: 1, total: 2 } }),
      ),
    );
    render(<Lorebook />);

    expect(await screen.findByRole('button', { name: /study · discovered/i })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /pets · not yet discovered/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pets/i })).not.toBeInTheDocument();
  });

  it('opens details for an unlocked entry', async () => {
    server.use(
      http.get('*/api/lorebook/', () =>
        HttpResponse.json({ entries, counts: { unlocked: 1, total: 2 } }),
      ),
    );
    const user = userEvent.setup();
    render(<Lorebook />);

    await user.click(await screen.findByRole('button', { name: /study · discovered/i }));
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /study/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/homework pays no money/i)).toBeInTheDocument();
  });
});
