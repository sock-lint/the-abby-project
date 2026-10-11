import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, renderWithProviders, screen, userEvent } from '../../test/render';
import TomeShelf from './TomeShelf';

const items = [
  { id: 1, name: 'Woodworking', icon: '🪵' },
  { id: 2, name: 'Pottery', icon: '🏺' },
  { id: 3, name: 'Sewing', icon: '🧵' },
];

describe('TomeShelf', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    Element.prototype.scrollTo = vi.fn();
  });

  it('exposes a horizontal tablist with the supplied ariaLabel', () => {
    renderWithProviders(
      <TomeShelf
        items={items}
        activeId={1}
        onSelect={() => {}}
        ariaLabel="Skill categories"
      />,
    );
    const list = screen.getByRole('tablist', { name: /skill categories/i });
    expect(list).toHaveAttribute('aria-orientation', 'horizontal');
  });

  it('renders one tab per item with the active one marked', () => {
    renderWithProviders(
      <TomeShelf items={items} activeId={2} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tab', { name: /Pottery/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: /Woodworking/ })).toHaveAttribute(
      'aria-selected',
      'false',
    );
  });

  it('centers the active tome within its rail without scrolling the page or stealing focus', () => {
    const { rerender } = render(
      <TomeShelf items={items} activeId={1} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    expect(screen.getByRole('tab', { name: /Woodworking/ })).not.toHaveFocus();
    const shelf = screen.getByRole('tablist');
    Object.defineProperty(shelf, 'clientWidth', { value: 200 });
    shelf.getBoundingClientRect = () => ({ left: 10 });
    screen.getByRole('tab', { name: /Sewing/ }).getBoundingClientRect = () => ({ left: 320, width: 100 });
    Element.prototype.scrollTo.mockClear();
    rerender(
      <TomeShelf items={items} activeId={3} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ left: 260, behavior: 'smooth' });
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(screen.getByRole('tab', { name: /Sewing/ })).not.toHaveFocus();
  });

  it('calls onSelect with the item id when a tome is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TomeShelf items={items} activeId={1} onSelect={spy} ariaLabel="Shelves" />,
    );
    await user.click(screen.getByRole('tab', { name: /Pottery/ }));
    expect(spy).toHaveBeenCalledWith(2);
  });

  it('moves selection with ArrowRight and wraps with ArrowLeft', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TomeShelf items={items} activeId={1} onSelect={spy} ariaLabel="Shelves" />,
    );
    screen.getByRole('tab', { name: /Woodworking/ }).focus();
    await user.keyboard('{ArrowRight}');
    expect(spy).toHaveBeenCalledWith(2);
    spy.mockClear();
    await user.keyboard('{ArrowLeft}');
    expect(spy).toHaveBeenCalledWith(3);
  });

  it('renders a wooden shelf board under the row of tomes', () => {
    // Library of Mastery — the spines need somewhere to sit. Queryable
    // via data-shelf-board so any future shelf-redesign that drops the
    // plank fails loud rather than silently flattening the metaphor.
    const { container } = renderWithProviders(
      <TomeShelf items={items} activeId={1} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    expect(container.querySelector('[data-shelf-board="true"]')).not.toBeNull();
  });

  it('renders nothing when there are no items', () => {
    const { container } = renderWithProviders(
      <TomeShelf items={[]} activeId={null} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    expect(container.querySelector('[role="tablist"]')).toBeNull();
  });

  describe('vessel pill row (phone-aware filters)', () => {
    const vesselItems = [
      { id: 'all', name: 'All', icon: '✦', chip: '×3', variant: 'vessel' },
      { id: 'boss', name: 'Boss', icon: '🐲', chip: '×2', variant: 'vessel' },
      { id: 'collection', name: 'Collection', icon: '🍓', chip: '×1', variant: 'vessel' },
    ];

    it('renders a pill row alongside the spine rail when every item is a vessel', () => {
      const { container } = renderWithProviders(
        <TomeShelf
          items={vesselItems}
          activeId="all"
          onSelect={() => {}}
          ariaLabel="Filter trials by kind"
        />,
      );
      // Pill row exists and is mobile-only; the spine rail stays in the DOM
      // (CSS-hidden below md) so tab-role queries keep working.
      const pillRow = container.querySelector('[data-vessel-pills="true"]');
      expect(pillRow).not.toBeNull();
      expect(pillRow.className).toMatch(/md:hidden/);
      // An all-vessel shelf is a cabinet, not a plank: drawers are housed in
      // a case, where tomes stand on a board. Sharing the board was part of
      // why the two variants read as the same object.
      expect(container.querySelector('[data-shelf-board="true"]')).toBeNull();
      const shelfWrap = container.querySelector('[data-shelf-case="true"]').parentElement;
      expect(shelfWrap.classList.contains('hidden')).toBe(true);
      expect(shelfWrap.classList.contains('md:block')).toBe(true);
      // Spines keep the tablist/tab contract...
      expect(screen.getAllByRole('tab')).toHaveLength(3);
      // ...while pills are plain buttons with aria-pressed — never a second
      // set of tabs for the same picker.
      const pills = screen.getAllByRole('button');
      expect(pills).toHaveLength(3);
      expect(pills[0]).toHaveAttribute('aria-pressed', 'true');
      expect(pills[1]).toHaveAttribute('aria-pressed', 'false');
    });

    it('fires the same onSelect from a pill tap', async () => {
      const user = userEvent.setup();
      const spy = vi.fn();
      renderWithProviders(
        <TomeShelf
          items={vesselItems}
          activeId="all"
          onSelect={spy}
          ariaLabel="Filter trials by kind"
        />,
      );
      await user.click(screen.getByRole('button', { name: 'Boss' }));
      expect(spy).toHaveBeenCalledWith('boss');
    });

    it('does not render a pill row for codex/category shelves', () => {
      const { container } = renderWithProviders(
        <TomeShelf items={items} activeId={1} onSelect={() => {}} ariaLabel="Shelves" />,
      );
      expect(container.querySelector('[data-vessel-pills="true"]')).toBeNull();
      const shelfWrap = container.querySelector('[data-shelf-board="true"]').parentElement;
      expect(shelfWrap.classList.contains('hidden')).toBe(false);
    });
  });
});
