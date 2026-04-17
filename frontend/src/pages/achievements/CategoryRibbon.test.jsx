import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import CategoryRibbon from './CategoryRibbon';

const categories = [
  { id: 1, name: 'Woodworking', icon: '🪵' },
  { id: 2, name: 'Pottery', icon: '🏺' },
  { id: 3, name: 'Sewing', icon: '🧵' },
];

describe('CategoryRibbon', () => {
  beforeEach(() => {
    // scrollIntoView is not implemented in jsdom — stub so selection side-effects don't throw.
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('exposes a horizontal tablist', () => {
    renderWithProviders(
      <CategoryRibbon categories={categories} activeId={1} onSelect={() => {}} />,
    );
    const list = screen.getByRole('tablist');
    expect(list).toHaveAttribute('aria-orientation', 'horizontal');
  });

  it('renders one tab per category with the active one marked', () => {
    renderWithProviders(
      <CategoryRibbon categories={categories} activeId={2} onSelect={() => {}} />,
    );
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    const pottery = screen.getByRole('tab', { name: /Pottery/ });
    expect(pottery).toHaveAttribute('aria-selected', 'true');
    const wood = screen.getByRole('tab', { name: /Woodworking/ });
    expect(wood).toHaveAttribute('aria-selected', 'false');
  });

  it('scrolls the active tab into view when activeId changes', () => {
    const { rerender } = renderWithProviders(
      <CategoryRibbon categories={categories} activeId={1} onSelect={() => {}} />,
    );
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;
    rerender(<CategoryRibbon categories={categories} activeId={3} onSelect={() => {}} />);
    expect(spy).toHaveBeenCalled();
    const call = spy.mock.calls[0];
    expect(call[0]).toMatchObject({ inline: 'center', block: 'nearest' });
  });

  it('calls onSelect when a tab is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <CategoryRibbon categories={categories} activeId={1} onSelect={spy} />,
    );
    await user.click(screen.getByRole('tab', { name: /Pottery/ }));
    expect(spy).toHaveBeenCalledWith(2);
  });

  it('moves selection with ArrowRight and ArrowLeft', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <CategoryRibbon categories={categories} activeId={1} onSelect={spy} />,
    );
    const wood = screen.getByRole('tab', { name: /Woodworking/ });
    wood.focus();
    await user.keyboard('{ArrowRight}');
    expect(spy).toHaveBeenCalledWith(2);
    spy.mockClear();
    await user.keyboard('{ArrowLeft}');
    expect(spy).toHaveBeenCalledWith(3); // wraps
  });

  it('renders nothing useful when categories is empty', () => {
    renderWithProviders(<CategoryRibbon categories={[]} activeId={null} onSelect={() => {}} />);
    expect(screen.queryByRole('tab')).toBeNull();
  });
});
