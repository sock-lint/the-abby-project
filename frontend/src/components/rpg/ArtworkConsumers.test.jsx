import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen } from '../../test/render';
import { server } from '../../test/server';
import { resolveArtworkImage } from '../../catalog/sharedArtwork';
import BadgeSigil from '../atlas/BadgeSigil';
import BadgeArtwork from '../atlas/BadgeArtwork';
import SkillTreeView from '../../pages/achievements/SkillTreeView';
import SkillVerse from '../../pages/achievements/SkillVerse';
import SkillDetailSheet from '../../pages/achievements/SkillDetailSheet';
import FolioSpread from '../../pages/achievements/FolioSpread';
import BirthdayCelebrationModal from '../BirthdayCelebrationModal';
import ChildDashboard from '../../pages/ChildDashboard';
import TrophySlot from '../../pages/character/TrophySlot';
import artworkBadges from '../../../../contracts/api/fixtures/artwork-badges.json';
import artworkCharacter from '../../../../contracts/api/fixtures/artwork-character.json';
import artworkCategories from '../../../../contracts/api/fixtures/artwork-categories.json';
import artworkSubjects from '../../../../contracts/api/fixtures/artwork-subjects.json';
import artworkSkills from '../../../../contracts/api/fixtures/artwork-skills.json';
import artworkTree from '../../../../contracts/api/fixtures/artwork-tree.json';

vi.mock('../../catalog/sharedArtwork', () => ({
  BIRTHDAY_ARTWORK_ID: 'birthday-candle', resolveArtworkImage: vi.fn(),
}));
vi.mock('framer-motion', async () => ({ ...await vi.importActual('framer-motion'), AnimatePresence: ({ children }) => children }));

const skill = { id: 31, name: 'Hand Tools', icon: '🪚✨', catalog_icon: 'skill-hand-tools',
  unlocked: false, level: 0, xp_points: 0, prerequisites: [], level_names: {} };
const category = { id: 11, name: 'Woodworking', icon: '🪵', catalog_icon: 'category-woodworking' };
const subject = { id: 21, name: 'Shop Basics', icon: '🔨', catalog_icon: 'subject-shop-basics', category: 11, skills: [skill] };
const tree = { category, summary: { level: 0, total_xp: 0 }, subjects: [subject] };
const badge = { id: 5, name: 'Night Owl', icon: '🦉✨', catalog_icon: 'badge-night-owl', rarity: 'rare' };
const imageFor = (container, id) => container.querySelector(`img[data-artwork-image="${id}"]`);

beforeEach(() => resolveArtworkImage.mockReset().mockImplementation((id) => id ? { url: `/synthetic/${id}.png` } : null));

describe('Server-confirmed artwork consumers', () => {
  it('renders shared badge and trophy fixtures while preserving a known-name badge whose changed criterion has no art', () => {
    const onOpen = vi.fn();
    const { container } = renderWithProviders(<>
      {artworkBadges.results.map((entry) => <BadgeSigil key={entry.id} badge={entry} earned={entry.id === 501} />)}
      <TrophySlot badge={artworkCharacter.active_trophy_badge} onOpen={onOpen} />
    </>);
    expect(container.querySelectorAll('img[data-artwork-image="badge-10-hour-club"]')).toHaveLength(2);
    const custom = screen.getByRole('button', { name: '25-Hour Club · rare · not yet earned' });
    expect(within(custom).getByText('CUSTOM BADGE')).toBeInTheDocument();
    expect(custom.querySelector('img[data-artwork-image]')).toBeNull();
    expect(screen.getByRole('button', { name: 'Trophy badge: 10-Hour Club. Click to change or clear.' }))
      .toHaveAttribute('data-filled', 'true');
  });

  it('uses the real shared skill-tree fixture and retains its server XP, unlocked state and names', async () => {
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json(artworkSubjects)),
      http.get('*/api/skills/', () => HttpResponse.json(artworkSkills)),
      http.get('*/api/skills/tree/101/', () => HttpResponse.json(artworkTree)),
    );
    const { container, user } = renderWithProviders(<SkillTreeView categories={artworkCategories.results} />);
    const custom = screen.getByRole('button', { name: 'Custom Coding' });
    expect(within(custom).getByText('CUSTOM')).toBeInTheDocument();
    expect(custom.querySelector('img[data-artwork-image]')).toBeNull();
    await user.click(screen.getByRole('button', { name: /^Coding(?:,|$)/ }));
    await user.click(await screen.findByRole('button', { name: 'Languages & Apps, 1 skill' }));
    await user.click(screen.getByRole('button', { name: /Python, level 1, 25% toward level 2/ }));
    expect(screen.getByRole('heading', { name: 'Python' })).toBeInTheDocument();
    expect(imageFor(container, 'skill-coding-python')).toBeInTheDocument();
    expect(screen.getByText('Level 1 · 150 XP')).toBeInTheDocument();
    expect(screen.queryByText('This skill is locked and has not unlocked yet.')).toBeNull();
  });

  it('retains badge name, rarity and unearned state while showing new art and recovering the full glyph', () => {
    const { container, beat } = renderWithProviders(<BadgeSigil badge={badge} earned={false} />);
    expect(screen.getByRole('button', { name: 'Night Owl · rare · not yet earned' })).toBeInTheDocument();
    const image = imageFor(container, badge.catalog_icon);
    expect(image).toHaveAttribute('src', '/synthetic/badge-night-owl.png');
    expect(image.closest('.grayscale')).not.toBeNull();
    fireEvent.error(image);
    expect(screen.getByText('🦉✨')).toBeInTheDocument();
    beat(null);
    expect(imageFor(container, badge.catalog_icon)).toBeNull();
  });

  it('never assigns known badge art to a same-name custom record without a server reference', () => {
    const { container } = renderWithProviders(<BadgeArtwork badge={{ ...badge, catalog_icon: null }} earned />);
    expect(imageFor(container, badge.catalog_icon)).toBeNull();
    expect(screen.getByText('🦉✨')).toBeInTheDocument();
  });

  it('carries server references through category, subject, locked skill and skill-detail navigation', async () => {
    server.use(
      http.get('*/api/subjects/', () => HttpResponse.json([subject])),
      http.get('*/api/skills/', () => HttpResponse.json([{ ...skill, category: 11, subject: 21 }])),
      http.get('*/api/skills/tree/11/', () => HttpResponse.json(tree)),
    );
    const { container, user } = renderWithProviders(<SkillTreeView categories={[category]} />);
    expect(imageFor(container, category.catalog_icon)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    await screen.findByRole('button', { name: 'Shop Basics, 1 skill' });
    expect(imageFor(container, category.catalog_icon)).toBeInTheDocument();
    expect(imageFor(container, subject.catalog_icon)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Shop Basics, 1 skill' }));
    const locked = screen.getByRole('button', { name: /Hand Tools, locked/ });
    expect(imageFor(locked, skill.catalog_icon)).toBeInTheDocument();
    expect(locked).toHaveAttribute('data-locked', 'true');
    await user.click(locked);
    await screen.findByRole('heading', { name: 'Hand Tools' });
    expect(imageFor(container, skill.catalog_icon)).toBeInTheDocument();
    expect(screen.getByText('This skill is locked and has not unlocked yet.')).toBeInTheDocument();
  });

  it('keeps initials for a glyph-free custom skill without inventing known art', () => {
    const { container } = renderWithProviders(<SkillVerse variant="wayfinder" skill={{ ...skill, icon: '', catalog_icon: null }} />);
    expect(screen.getByText('H')).toBeInTheDocument();
    expect(container.querySelector('img[data-artwork-image]')).toBeNull();
  });

  it('uses the same server skill art and locked progression in the retained skill sheet', () => {
    renderWithProviders(<SkillDetailSheet skill={skill} onClose={() => {}} />);
    const dialog = screen.getByRole('dialog', { name: 'Hand Tools' });
    expect(imageFor(dialog, skill.catalog_icon)).toBeInTheDocument();
    expect(screen.getByText('Complete the required skills to unlock this skill.')).toBeInTheDocument();
  });

  it('carries category, subject and skill art into the retained folio without changing XP', () => {
    const { container } = renderWithProviders(<FolioSpread tree={tree} />);
    for (const id of [category.catalog_icon, subject.catalog_icon, skill.catalog_icon]) expect(imageFor(container, id)).toBeInTheDocument();
    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Hand Tools, locked/ })).toBeInTheDocument();
  });

  it('shows the candle at 64 CSS pixels and retains age, rewards, dismissal and placeholder recovery', async () => {
    const onDismiss = vi.fn();
    const { user } = renderWithProviders(<BirthdayCelebrationModal entry={{ id: 42, title: 'Turned 15', metadata: { gift_coins: 1500 } }} onDismiss={onDismiss} />);
    const dialog = screen.getByRole('alertdialog', { name: 'Happy birthday' });
    const image = imageFor(dialog, 'birthday-candle');
    expect(image).toHaveStyle({ width: '64px', height: '64px' });
    expect(image).toHaveAttribute('alt', '');
    expect(within(dialog).getByText('15')).toBeInTheDocument();
    expect(within(dialog).getByText(/1500 coins/)).toBeInTheDocument();
    fireEvent.error(image);
    expect(dialog.querySelector('img')).toHaveAttribute('src', expect.stringContaining('birthday-candle-placeholder.png'));
    await user.click(within(dialog).getByRole('button', { name: /Turn the page/ }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('routes Today recent badge artwork through the same quiet badge renderer and preserves its navigation name', async () => {
    const { container, user } = renderWithProviders(<ChildDashboard data={{ next_actions: [], recent_badges: [{ badge__id: badge.id,
      badge__name: badge.name, badge__icon: badge.icon, badge__catalog_icon: badge.catalog_icon }] }} />);
    await user.click(screen.getByRole('button', { name: /Recent badges/ }));
    const button = screen.getByRole('button', { name: 'Night Owl — view earned badges' });
    expect(button.querySelector('[data-badge-artwork="tile"]')).toBeInTheDocument();
    expect(imageFor(container, badge.catalog_icon)).toBeInTheDocument();
  });
});
