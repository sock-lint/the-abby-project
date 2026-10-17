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
  it('disables every owned frame choice while a change is pending', () => {
    const frames = [{ id: 1, name: 'Bronze Frame' }, { id: 2, name: 'Silver Frame' }];
    renderWithProviders(<CosmeticChapter chapter={frameChapter} owned={frames} catalog={frames}
      activeId={1} busy={1} onEquip={() => {}} onUnequip={() => {}} />);
    expect(screen.getByRole('button', { name: /Bronze Frame/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Silver Frame/ })).toBeDisabled();
  });
  it('renders the rubric, drop-cap, name, kicker, and owned-count chip', () => {
    const { container } = renderWithProviders(
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
    expect(container.querySelector('[data-chapter-marker="1"]')).toHaveTextContent('1');
    expect(screen.getByText('Your equipped frame outlines your profile picture and styles your featured badge when a card style is available.')).toBeInTheDocument();
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
