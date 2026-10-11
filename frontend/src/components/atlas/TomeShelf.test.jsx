import { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, userEvent } from '../../test/render';
import TomeShelf from './TomeShelf';

const items = [
  { id: 1, name: 'Woodworking', icon: '🪵' },
  { id: 2, name: 'Pottery', icon: '🏺' },
  { id: 3, name: 'Sewing', icon: '🧵' },
];
const vesselItems = [
  { id: 'all', name: 'All', icon: '✦', chip: '×3', variant: 'vessel' },
  { id: 'boss', name: 'Boss', icon: '🐲', chip: '×2', variant: 'vessel' },
  { id: 'collection', name: 'Collection', icon: '🍓', chip: '×1', variant: 'vessel' },
];

function ControlledShelf({ descriptors = items, initialId = descriptors[0].id, onSelect = () => {} }) {
  const [activeId, setActiveId] = useState(initialId);
  return (
    <TomeShelf
      items={descriptors}
      activeId={activeId}
      onSelect={(id) => { setActiveId(id); onSelect(id); }}
      ariaLabel="Collections"
    />
  );
}

describe('TomeShelf', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    Element.prototype.scrollTo = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  it('exposes one horizontal tablist and one control per collection', () => {
    const { container } = render(<ControlledShelf initialId={2} />);
    expect(screen.getAllByRole('tablist')).toHaveLength(1);
    expect(screen.getByRole('tablist', { name: 'Collections' })).toHaveAttribute('aria-orientation', 'horizontal');
    expect(screen.getAllByRole('tab')).toHaveLength(items.length);
    expect(container.querySelectorAll('button')).toHaveLength(items.length);
    expect(screen.getByRole('tab', { name: 'Pottery' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Woodworking' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getAllByRole('tab').filter((tab) => tab.tabIndex === 0)).toEqual([
      screen.getByRole('tab', { name: 'Pottery' }),
    ]);
  });

  it('selects a collection when clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ControlledShelf onSelect={onSelect} />);
    await user.click(screen.getByRole('tab', { name: 'Pottery' }));
    expect(onSelect).toHaveBeenCalledWith(2);
    expect(screen.getByRole('tab', { name: 'Pottery' })).toHaveAttribute('aria-selected', 'true');
  });

  it('wraps Left/Right selection and focus with one tab stop', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ControlledShelf onSelect={onSelect} />);
    const first = screen.getByRole('tab', { name: 'Woodworking' });
    const last = screen.getByRole('tab', { name: 'Sewing' });
    first.getBoundingClientRect = last.getBoundingClientRect = () => ({
      top: 120, bottom: 260, left: 20, right: 300,
    });
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');
    first.focus();
    await user.keyboard('{ArrowLeft}');
    expect(last).toHaveFocus();
    expect(last).toHaveAttribute('aria-selected', 'true');
    expect(onSelect).toHaveBeenLastCalledWith(3);
    await user.keyboard('{ArrowRight}');
    expect(first).toHaveFocus();
    expect(onSelect).toHaveBeenLastCalledWith(1);
    expect(focus).toHaveBeenLastCalledWith({ preventScroll: true });
    expect(screen.getAllByRole('tab').filter((tab) => tab.tabIndex === 0)).toEqual([first]);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
  });

  it('reveals an offscreen keyboard destination with only the nearest necessary scroll', async () => {
    const user = userEvent.setup();
    render(<ControlledShelf />);
    const first = screen.getByRole('tab', { name: 'Woodworking' });
    const last = screen.getByRole('tab', { name: 'Sewing' });
    last.getBoundingClientRect = () => ({
      top: window.innerHeight + 20, bottom: window.innerHeight + 160, left: 20, right: 300,
    });
    first.getBoundingClientRect = () => ({ top: 120, bottom: 260, left: 20, right: 300 });
    first.focus();
    await user.keyboard('{End}');
    expect(last).toHaveFocus();
    expect(last).toHaveAttribute('aria-selected', 'true');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledExactlyOnceWith({
      block: 'nearest', inline: 'nearest', behavior: 'instant',
    });
    Element.prototype.scrollIntoView.mockClear();
    await user.keyboard('{Home}');
    expect(first).toHaveFocus();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it('selects and focuses the first/last collection with Home/End', async () => {
    const user = userEvent.setup();
    render(<ControlledShelf initialId={2} />);
    screen.getByRole('tab', { name: 'Pottery' }).focus();
    await user.keyboard('{End}');
    expect(screen.getByRole('tab', { name: 'Sewing' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: 'Sewing' })).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{Home}');
    expect(screen.getByRole('tab', { name: 'Woodworking' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: 'Woodworking' })).toHaveAttribute('aria-selected', 'true');
  });

  it.each(['header', 'bottom nav'])('reveals a keyboard target obscured by the %s inside the raw viewport', async (occlusion) => {
    const user = userEvent.setup();
    const { container } = render(
      <>
        <div data-journal-sticky-header="true" />
        <ControlledShelf />
        <div data-journal-bottom-nav="true" />
      </>,
    );
    container.querySelector('[data-journal-sticky-header="true"]').getBoundingClientRect = () => ({
      top: 0, bottom: 80, height: 80,
    });
    container.querySelector('[data-journal-bottom-nav="true"]').getBoundingClientRect = () => ({
      top: window.innerHeight - 64, bottom: window.innerHeight, height: 64,
    });
    const last = screen.getByRole('tab', { name: 'Sewing' });
    last.getBoundingClientRect = () => occlusion === 'header'
      ? { top: 20, bottom: 70, left: 20, right: 300 }
      : { top: window.innerHeight - 100, bottom: window.innerHeight - 20, left: 20, right: 300 };
    screen.getByRole('tab', { name: 'Woodworking' }).focus();
    await user.keyboard('{End}');
    expect(last).toHaveFocus();
    expect(last).toHaveStyle({ scrollMarginTop: '84px', scrollMarginBottom: '68px' });
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledExactlyOnceWith({
      block: 'nearest', inline: 'nearest', behavior: 'instant',
    });
  });

  it('ignores hidden shell chrome when revealing keyboard selections', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <>
        <div data-journal-sticky-header="true" />
        <ControlledShelf />
        <div data-journal-bottom-nav="true" />
      </>,
    );
    for (const marker of container.querySelectorAll('[data-journal-sticky-header], [data-journal-bottom-nav]')) {
      marker.getBoundingClientRect = () => ({ top: 0, bottom: 80, height: 0 });
    }
    const last = screen.getByRole('tab', { name: 'Sewing' });
    last.getBoundingClientRect = () => ({ top: 20, bottom: 70, left: 20, right: 300 });
    screen.getByRole('tab', { name: 'Woodworking' }).focus();
    await user.keyboard('{End}');
    expect(last).toHaveStyle({ scrollMarginTop: '4px', scrollMarginBottom: '4px' });
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it('navigates from the focused control even before the parent accepts a selection', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<TomeShelf items={items} activeId={1} onSelect={onSelect} ariaLabel="Collections" />);
    screen.getByRole('tab', { name: 'Woodworking' }).focus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    expect(onSelect.mock.calls.map(([id]) => id)).toEqual([2, 3]);
    expect(screen.getByRole('tab', { name: 'Sewing' })).toHaveFocus();
  });

  it('retains a reachable first control when the active ID is missing or removed', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { rerender } = render(<TomeShelf items={items} activeId="missing" onSelect={onSelect} ariaLabel="Collections" />);
    const first = screen.getByRole('tab', { name: 'Woodworking' });
    expect(first).toHaveAttribute('tabindex', '0');
    expect(screen.getAllByRole('tab').every((tab) => tab.getAttribute('aria-selected') === 'false')).toBe(true);
    await user.tab();
    expect(first).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(onSelect).toHaveBeenCalledWith(3);
    rerender(<TomeShelf items={items.slice(0, 2)} activeId={3} onSelect={onSelect} ariaLabel="Collections" />);
    expect(screen.getByRole('tab', { name: 'Woodworking' })).toHaveAttribute('tabindex', '0');
  });

  it('never steals focus or scrolls the page on mount or external selection', () => {
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');
    const view = (activeId) => (
      <>
        <div data-journal-sticky-header="true" />
        <TomeShelf items={items} activeId={activeId} onSelect={() => {}} ariaLabel="Collections" />
        <div data-journal-bottom-nav="true" />
      </>
    );
    const { container, rerender } = render(view(1));
    expect(focus).not.toHaveBeenCalled();
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab.style.scrollMarginTop).toBe('');
      expect(tab.style.scrollMarginBottom).toBe('');
    }
    screen.getByRole('tab', { name: 'Woodworking' }).focus();
    focus.mockClear();
    container.querySelector('[data-journal-sticky-header]').getBoundingClientRect = () => ({ top: 0, bottom: 80, height: 80 });
    container.querySelector('[data-journal-bottom-nav]').getBoundingClientRect = () => ({
      top: window.innerHeight - 64, bottom: window.innerHeight, height: 64,
    });
    rerender(view(3));
    expect(screen.getByRole('tab', { name: 'Woodworking' })).toHaveFocus();
    expect(focus).not.toHaveBeenCalled();
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab.style.scrollMarginTop).toBe('');
      expect(tab.style.scrollMarginBottom).toBe('');
    }
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
  });

  it('uses one wrapping pill tablist for vessel filters with the same keyboard behavior', async () => {
    const user = userEvent.setup();
    const { container } = render(<ControlledShelf descriptors={vesselItems} />);
    expect(screen.getAllByRole('tablist')).toHaveLength(1);
    expect(screen.getByRole('tablist')).toHaveAttribute('data-collection-layout', 'pills');
    expect(screen.getAllByRole('tab')).toHaveLength(vesselItems.length);
    expect(container.querySelectorAll('button')).toHaveLength(vesselItems.length);
    expect(screen.getByRole('tab', { name: 'Boss, ×2' })).toHaveAttribute('data-spine-variant', 'vessel');
    screen.getByRole('tab', { name: 'All, ×3' }).focus();
    await user.keyboard('{End}');
    expect(screen.getByRole('tab', { name: 'Collection, ×1' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: 'Collection, ×1' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'Boss, ×2' }));
    expect(screen.getByRole('tab', { name: 'Boss, ×2' })).toHaveAttribute('aria-selected', 'true');
  });

  it('renders mixed category/filter descriptors as one card collection', () => {
    render(<ControlledShelf descriptors={[items[0], vesselItems[0]]} />);
    expect(screen.getByRole('tablist')).toHaveAttribute('data-collection-layout', 'cards');
    expect(screen.getAllByRole('tab')).toHaveLength(2);
  });

  it('ignores unrelated keys and renders no controls for an empty collection', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { rerender } = render(<ControlledShelf onSelect={onSelect} />);
    screen.getByRole('tab', { name: 'Woodworking' }).focus();
    await user.keyboard('{ArrowDown}');
    expect(onSelect).not.toHaveBeenCalled();
    rerender(<TomeShelf items={[]} activeId={null} onSelect={onSelect} ariaLabel="Collections" />);
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });
});
