import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import CosmeticChapter from './CosmeticChapter';
import { COSMETIC_CHAPTERS_BY_SLOT } from './character.constants';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const frameChapter = COSMETIC_CHAPTERS_BY_SLOT.active_frame;

describe('CosmeticChapter', () => {
  it('renders the rubric, drop-cap, name, kicker, and owned-count chip', () => {
    renderWithProviders(
      <CosmeticChapter
        chapter={frameChapter}
        owned={[{ id: 1, name: 'Bronze Frame', rarity: 'common' }]}
        catalog={[
          { id: 1, name: 'Bronze Frame', rarity: 'common' },
          { id: 2, name: 'Silver Frame', rarity: 'uncommon' },
        ]}
        activeId={null}
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    expect(screen.getByRole('region', { name: frameChapter.name })).toBeInTheDocument();
    expect(screen.getByText('\u00a7I')).toBeInTheDocument();
    expect(screen.getByText(/a border of renown/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 2/)).toBeInTheDocument();
  });

  it('lists both owned and un-owned sigils in the same chapter', () => {
    renderWithProviders(
      <CosmeticChapter
        chapter={frameChapter}
        owned={[{ id: 1, name: 'Bronze Frame', rarity: 'common' }]}
        catalog={[
          { id: 1, name: 'Bronze Frame', rarity: 'common' },
          { id: 2, name: 'Silver Frame', rarity: 'uncommon' },
        ]}
        activeId={null}
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    expect(screen.getByText('Bronze Frame')).toBeInTheDocument();
    expect(screen.getByText('Silver Frame')).toBeInTheDocument();
  });

  it('shows a whisper when the catalog is empty', () => {
    renderWithProviders(
      <CosmeticChapter
        chapter={frameChapter}
        owned={[]}
        catalog={[]}
        activeId={null}
        onEquip={() => {}}
        onUnequip={() => {}}
      />,
    );
    expect(screen.getByText(/no cosmetics authored yet/i)).toBeInTheDocument();
  });
});
