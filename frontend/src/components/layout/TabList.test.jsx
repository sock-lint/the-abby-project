import { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useReducedMotion } from 'framer-motion';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TabList from './TabList';

vi.mock('framer-motion', async () => ({
  ...await vi.importActual('framer-motion'),
  useReducedMotion: vi.fn(() => false),
}));

beforeEach(() => {
  vi.mocked(useReducedMotion).mockReturnValue(false);
  Element.prototype.scrollTo = vi.fn();
});

const tabs = [
  { id: 'a', label: 'Alpha' },
  { id: 'b', label: 'Beta' },
  { id: 'c', label: 'Gamma' },
];

describe('TabList', () => {
  it('keeps one tab stop and moves focus and selection with arrows, Home and End', async () => {
    const user = userEvent.setup();
    function Hub() {
      const [active, setActive] = useState('b');
      return <TabList tabs={tabs} activeId={active} onSelect={setActive} ariaLabel="Hub" />;
    }
    render(<Hub />);
    const alpha = screen.getByRole('tab', { name: 'Alpha' });
    const beta = screen.getByRole('tab', { name: 'Beta' });
    const gamma = screen.getByRole('tab', { name: 'Gamma' });
    expect(alpha.tabIndex).toBe(-1);
    expect(beta.tabIndex).toBe(0);
    expect(gamma.tabIndex).toBe(-1);
    await user.tab();
    expect(beta).toHaveFocus();
    await user.keyboard('{ArrowRight}');
    expect(gamma).toHaveFocus();
    expect(gamma).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{ArrowRight}');
    expect(alpha).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(gamma).toHaveFocus();
    await user.keyboard('{Home}');
    expect(alpha).toHaveFocus();
    await user.keyboard('{End}');
    expect(gamma).toHaveFocus();
    expect(gamma.tabIndex).toBe(0);
    expect(alpha.tabIndex).toBe(-1);
    await user.tab();
    expect(gamma).not.toHaveFocus();
  });

  it('allows keyboard entry when the active id is missing', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<TabList tabs={tabs} activeId="unknown" onSelect={onSelect} ariaLabel="Hub" />);
    await user.tab();
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveFocus();
    await user.keyboard('{ArrowRight}');
    expect(onSelect).toHaveBeenCalledWith('b');
  });

  it('reveals the active tab without smooth scrolling when motion is reduced', () => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
    const pageScroll = vi.spyOn(Element.prototype, 'scrollIntoView');
    render(<TabList tabs={tabs} activeId="b" onSelect={() => {}} ariaLabel="Hub" />);
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ behavior: 'auto', left: 0 });
    expect(pageScroll).not.toHaveBeenCalled();
    pageScroll.mockRestore();
  });

  it('exposes a tablist with the supplied ariaLabel', () => {
    render(
      <TabList tabs={tabs} activeId="a" onSelect={() => {}} ariaLabel="Hub sections" />,
    );
    expect(screen.getByRole('tablist', { name: /Hub sections/i })).toBeInTheDocument();
  });

  it('renders one tab per descriptor with the active one marked', () => {
    render(
      <TabList tabs={tabs} activeId="b" onSelect={() => {}} ariaLabel="Hub" />,
    );
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'false');
  });

  it('calls onSelect with the descriptor id when a tab is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<TabList tabs={tabs} activeId="a" onSelect={spy} ariaLabel="Hub" />);
    await user.click(screen.getByRole('tab', { name: 'Gamma' }));
    expect(spy).toHaveBeenCalledWith('c');
  });

  it('applies the pill variant by default for pill variant', () => {
    render(
      <TabList
        tabs={tabs}
        activeId="a"
        onSelect={() => {}}
        variant="pill"
        ariaLabel="Hub"
      />,
    );
    const active = screen.getByRole('tab', { name: 'Alpha' });
    expect(active).toHaveClass('bg-sheikah-teal/15', 'text-ink-primary');
  });

  it('keeps the bookmark variant compatible with the shared rounded active pill', () => {
    render(
      <TabList
        tabs={tabs}
        activeId="b"
        onSelect={() => {}}
        variant="bookmark"
        ariaLabel="Hub"
      />,
    );
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveClass('rounded-full', 'bg-sheikah-teal/15', 'text-ink-primary');
  });

  it('renders icons in pill variant when descriptor includes one', () => {
    const Icon = ({ size }) => <svg data-testid="tab-icon" data-size={size} />;
    render(
      <TabList
        tabs={[{ id: 'a', label: 'Alpha', icon: Icon }]}
        activeId="a"
        onSelect={() => {}}
        variant="pill"
        ariaLabel="Hub"
      />,
    );
    expect(screen.getByTestId('tab-icon')).toBeInTheDocument();
  });

  it('stretch makes pill tabs grow to fill the strip width', () => {
    render(
      <TabList
        tabs={tabs}
        activeId="a"
        onSelect={() => {}}
        variant="pill"
        stretch
        ariaLabel="Hub"
      />,
    );
    expect(screen.getByRole('tab', { name: 'Alpha' }).className).toContain('flex-1');
  });
});
