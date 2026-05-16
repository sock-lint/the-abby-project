import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  // Strip motion-only props so jsdom doesn't choke on unknown DOM attributes.
  const MOTION_PROPS = new Set([
    'initial', 'animate', 'exit', 'transition', 'variants',
    'whileHover', 'whileTap', 'whileFocus', 'whileInView',
    'layout', 'layoutId',
  ]);
  return {
    ...actual,
    motion: new Proxy(
      {},
      {
        get: (_target, tag) => (props) => {
          const cleaned = {};
          for (const k in props) if (!MOTION_PROPS.has(k)) cleaned[k] = props[k];
          const Tag = tag;
          return <Tag data-motion-tag={tag} {...cleaned} />;
        },
      },
    ),
  };
});

import PageShell from './PageShell';

describe('PageShell', () => {
  it('renders children in a wide max-width container with default rhythm', () => {
    render(<PageShell><span>body</span></PageShell>);
    const body = screen.getByText('body');
    const shell = body.parentElement;
    expect(shell.className).toContain('max-w-6xl');
    expect(shell.className).toContain('space-y-5');
  });

  it('applies narrow width when width="narrow"', () => {
    render(<PageShell width="narrow"><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    expect(shell.className).toContain('max-w-3xl');
    expect(shell.className).not.toContain('max-w-6xl');
  });

  it('applies loose rhythm when rhythm="loose"', () => {
    render(<PageShell rhythm="loose"><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    expect(shell.className).toContain('space-y-6');
  });

  it('applies tight rhythm when rhythm="tight"', () => {
    render(<PageShell rhythm="tight"><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    expect(shell.className).toContain('space-y-3');
  });

  it('does not add horizontal padding (JournalShell owns it)', () => {
    render(<PageShell><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    // Outer page padding is owned by JournalShell to avoid double-padding;
    // PageShell only owns inner spine width + rhythm.
    expect(shell.className).not.toContain('px-3');
    expect(shell.className).not.toContain('sm:px-4');
  });

  it('skips motion wrapper when animate=false', () => {
    render(<PageShell animate={false}><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    expect(shell.getAttribute('data-motion-tag')).toBeNull();
  });

  it('renders as a motion element by default', () => {
    render(<PageShell><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    expect(shell.getAttribute('data-motion-tag')).toBe('div');
  });

  it('honors a custom className while keeping defaults', () => {
    render(<PageShell className="extra-rule"><span>body</span></PageShell>);
    const shell = screen.getByText('body').parentElement;
    expect(shell.className).toContain('extra-rule');
    expect(shell.className).toContain('max-w-6xl');
  });
});
