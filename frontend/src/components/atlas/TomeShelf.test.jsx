import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import TomeShelf from './TomeShelf';

const items = [
  { id: 1, name: 'Woodworking', icon: '🪵' },
  { id: 2, name: 'Pottery', icon: '🏺' },
  { id: 3, name: 'Sewing', icon: '🧵' },
];

describe('TomeShelf', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
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

  it('scrolls the active tome into view when activeId changes', () => {
    const { rerender } = renderWithProviders(
      <TomeShelf items={items} activeId={1} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;
    rerender(
      <TomeShelf items={items} activeId={3} onSelect={() => {}} ariaLabel="Shelves" />,
    );
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls[0][0]).toMatchObject({ inline: 'center', block: 'nearest' });
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
});
