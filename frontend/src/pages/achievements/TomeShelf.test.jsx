import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import TomeShelf from './TomeShelf';

const categories = [
  { id: 1, name: 'Woodworking', icon: '🪵' },
  { id: 2, name: 'Pottery', icon: '🏺' },
  { id: 3, name: 'Sewing', icon: '🧵' },
];

describe('TomeShelf', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('exposes a horizontal tablist', () => {
    renderWithProviders(
      <TomeShelf categories={categories} activeId={1} onSelect={() => {}} />,
    );
    const list = screen.getByRole('tablist');
    expect(list).toHaveAttribute('aria-orientation', 'horizontal');
  });

  it('renders one tab per category with the active one marked', () => {
    renderWithProviders(
      <TomeShelf categories={categories} activeId={2} onSelect={() => {}} />,
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
      <TomeShelf categories={categories} activeId={1} onSelect={() => {}} />,
    );
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;
    rerender(<TomeShelf categories={categories} activeId={3} onSelect={() => {}} />);
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls[0][0]).toMatchObject({ inline: 'center', block: 'nearest' });
  });

  it('calls onSelect with the category id when a tome is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TomeShelf categories={categories} activeId={1} onSelect={spy} />,
    );
    await user.click(screen.getByRole('tab', { name: /Pottery/ }));
    expect(spy).toHaveBeenCalledWith(2);
  });

  it('moves selection with ArrowRight and wraps with ArrowLeft', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TomeShelf categories={categories} activeId={1} onSelect={spy} />,
    );
    screen.getByRole('tab', { name: /Woodworking/ }).focus();
    await user.keyboard('{ArrowRight}');
    expect(spy).toHaveBeenCalledWith(2);
    spy.mockClear();
    await user.keyboard('{ArrowLeft}');
    expect(spy).toHaveBeenCalledWith(3);
  });

  it('renders nothing when there are no categories', () => {
    const { container } = renderWithProviders(
      <TomeShelf categories={[]} activeId={null} onSelect={() => {}} />,
    );
    expect(container.querySelector('[role="tablist"]')).toBeNull();
  });
});
