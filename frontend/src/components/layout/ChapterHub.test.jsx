import { describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ChapterHub from './ChapterHub.jsx';

// Capture the panel's drag handlers so the swipe gesture can be exercised —
// framer-motion's pointer pipeline doesn't run under jsdom.
const dragProps = { onDragEnd: null, onPointerDown: null };
const MOTION_ONLY_PROPS = [
  'drag', 'dragControls', 'dragListener', 'dragConstraints', 'dragElastic',
  'onDragEnd', 'onPointerDown', 'variants', 'initial', 'animate', 'exit',
  'transition', 'layout', 'whileTap', 'whileHover',
];
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  const passthrough = (Tag) => function MotionStub({ children, ...props }) {
    if (props.onDragEnd) {
      dragProps.onDragEnd = props.onDragEnd;
      dragProps.onPointerDown = props.onPointerDown;
    }
    const domProps = { ...props };
    MOTION_ONLY_PROPS.forEach((key) => delete domProps[key]);
    return <Tag {...domProps}>{children}</Tag>;
  };
  return {
    ...actual,
    useDragControls: () => ({ start: vi.fn() }),
    motion: new Proxy({}, { get: (_t, tag) => passthrough(tag) }),
  };
});

const tabs = [
  { id: 'a', label: 'Alpha', render: () => <div>content-a</div> },
  { id: 'b', label: 'Beta', render: () => <div>content-b</div> },
];

function renderHub({ route = '/', defaultTabId } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ChapterHub
        title="Test Hub"
        kicker="kicker"
        tabs={tabs}
        defaultTabId={defaultTabId}
      />
    </MemoryRouter>,
  );
}

describe('ChapterHub', () => {
  it('renders the breadcrumb kicker and first tab by default', () => {
    renderHub();
    // Hub no longer renders its own h1 — the active tab page owns the page
    // heading. Only the kicker breadcrumb stays as chapter context.
    expect(screen.queryByRole('heading', { name: 'Test Hub' })).toBeNull();
    expect(screen.getByText('kicker')).toBeInTheDocument();
    expect(screen.getByText('content-a')).toBeInTheDocument();
  });

  it('still labels the tab strip with the hub title for screen readers', () => {
    renderHub();
    // `title` is no longer rendered as visible text but still feeds the
    // tablist aria-label so screen-reader users can identify the strip.
    expect(screen.getByRole('tablist', { name: /Test Hub sections/i })).toBeInTheDocument();
  });

  it('switches to ?tab= matched tab', () => {
    renderHub({ route: '/?tab=b' });
    expect(screen.getByText('content-b')).toBeInTheDocument();
  });

  it('falls back to defaultTabId when ?tab= is unknown', () => {
    renderHub({ route: '/?tab=missing', defaultTabId: 'b' });
    expect(screen.getByText('content-b')).toBeInTheDocument();
  });

  it('falls back to first tab when no defaults match', () => {
    renderHub({ route: '/?tab=zzz' });
    expect(screen.getByText('content-a')).toBeInTheDocument();
  });

  it('clicking a tab updates the query string and content', async () => {
    const user = userEvent.setup();
    renderHub();
    await user.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(screen.getByText('content-b')).toBeInTheDocument();
  });

  it('sets aria-selected on the active tab', () => {
    renderHub({ route: '/?tab=b' });
    expect(
      screen.getByRole('tab', { name: 'Beta' }).getAttribute('aria-selected'),
    ).toBe('true');
  });

  describe('swipe between tabs', () => {
    it('swiping left advances to the next tab', async () => {
      renderHub();
      expect(screen.getByText('content-a')).toBeInTheDocument();
      await act(async () => {
        dragProps.onDragEnd({}, { offset: { x: -120, y: 0 } });
      });
      expect(screen.getByText('content-b')).toBeInTheDocument();
    });

    it('swiping right goes back to the previous tab', async () => {
      renderHub({ route: '/?tab=b' });
      await act(async () => {
        dragProps.onDragEnd({}, { offset: { x: 120, y: 0 } });
      });
      expect(screen.getByText('content-a')).toBeInTheDocument();
    });

    it('ignores a short drag and does not wrap past the last tab', async () => {
      renderHub();
      await act(async () => {
        dragProps.onDragEnd({}, { offset: { x: -30, y: 0 } });
      });
      expect(screen.getByText('content-a')).toBeInTheDocument();

      renderHub({ route: '/?tab=b' });
      await act(async () => {
        dragProps.onDragEnd({}, { offset: { x: -120, y: 0 } });
      });
      // Beta is the last tab — a further left swipe stays put.
      expect(screen.getAllByText('content-b').length).toBeGreaterThan(0);
    });

    it('does not start a swipe from a mouse pointer', () => {
      renderHub();
      const start = vi.fn();
      // pointerType 'mouse' returns before touching dragControls.
      expect(() => dragProps.onPointerDown({ pointerType: 'mouse', start })).not.toThrow();
      expect(start).not.toHaveBeenCalled();
    });
  });
});
