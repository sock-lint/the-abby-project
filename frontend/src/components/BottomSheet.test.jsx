import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BottomSheet from './BottomSheet.jsx';

afterEach(() => {
  vi.restoreAllMocks();
});

function renderDesktop(props = {}) {
  window.matchMedia = vi.fn().mockImplementation((q) => ({
    matches: q.includes('min-width'),
    media: q,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
  return render(
    <BottomSheet title="Title" onClose={() => {}} {...props}>
      <div>child</div>
    </BottomSheet>,
  );
}

function renderMobile(props = {}) {
  window.matchMedia = vi.fn().mockImplementation((q) => ({
    matches: false,
    media: q,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
  return render(
    <BottomSheet title="Title" onClose={() => {}} {...props}>
      <div>child</div>
    </BottomSheet>,
  );
}

describe('BottomSheet', () => {
  it('renders title + children on desktop', () => {
    renderDesktop();
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('child')).toBeInTheDocument();
  });

  it('renders title + children on mobile', () => {
    renderMobile();
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('child')).toBeInTheDocument();
  });

  it('calls onClose when the seal button is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderDesktop({ onClose });
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('disables the close button when disabled', () => {
    renderDesktop({ disabled: true });
    expect(screen.getByRole('button', { name: /close/i })).toBeDisabled();
  });

  it('reacts to matchMedia change events on mobile→desktop', () => {
    const handlers = {};
    window.matchMedia = vi.fn().mockImplementation((q) => ({
      matches: false,
      media: q,
      addEventListener: (_event, cb) => { handlers.cb = cb; },
      removeEventListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    }));
    render(
      <BottomSheet title="Flex" onClose={() => {}}>
        <div>child</div>
      </BottomSheet>,
    );
    // Trigger the mql.addEventListener('change', ...) callback.
    handlers.cb?.({ matches: true });
    // No throw; component should re-render without crashing.
    expect(screen.getByText('Flex')).toBeInTheDocument();
  });

  it('exposes role=dialog with aria-modal and a labeled title on desktop', () => {
    renderDesktop({ title: 'Edit reward' });
    const dialog = screen.getByRole('dialog', { name: 'Edit reward' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('exposes role=dialog with aria-modal and a labeled title on mobile', () => {
    renderMobile({ title: 'Add chore' });
    const dialog = screen.getByRole('dialog', { name: 'Add chore' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  describe('back-gesture handling', () => {
    it('pushes a sentinel history entry on open and closes on popstate', async () => {
      const onClose = vi.fn();
      const pushSpy = vi.spyOn(window.history, 'pushState');
      renderMobile({ onClose });

      // Opening arms the sentinel so a back press has something to pop.
      expect(pushSpy).toHaveBeenCalledWith(
        expect.objectContaining({ abbySheet: expect.anything() }),
        '',
      );

      await act(async () => {
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('keeps a dirty sheet open on back and re-arms the sentinel for the next press', async () => {
      const onClose = vi.fn();
      renderMobile({ onClose, dirty: true });
      const pushSpy = vi.spyOn(window.history, 'pushState');

      await act(async () => {
        window.dispatchEvent(new PopStateEvent('popstate'));
      });

      // Dirty sheets route through the discard guard rather than closing…
      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByRole('alertdialog', { name: /discard changes/i })).toBeInTheDocument();
      // …and back stays trapped for the next press.
      expect(pushSpy).toHaveBeenCalledWith(
        expect.objectContaining({ abbySheet: expect.anything() }),
        '',
      );
    });

    // Every other dismiss affordance checked `disabled`; the popstate handler
    // didn't, so Android back closed a sheet mid-save.
    it('leaves a saving sheet open on back', async () => {
      const onClose = vi.fn();
      renderMobile({ onClose, disabled: true });

      await act(async () => {
        window.dispatchEvent(new PopStateEvent('popstate'));
      });

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByRole('dialog', { name: 'Title' })).toBeInTheDocument();
    });

    // Busy consumers pass `onClose={busy ? undefined : onClose}`; back during a
    // submit used to call it and throw inside the popstate listener.
    it('does not throw when a busy sheet has no onClose handler', async () => {
      renderMobile({ onClose: undefined, disabled: true });

      await expect(act(async () => {
        window.dispatchEvent(new PopStateEvent('popstate'));
      })).resolves.not.toThrow();

      expect(screen.getByRole('dialog', { name: 'Title' })).toBeInTheDocument();
    });
  });

  describe('discard guard stacking', () => {
    it('does not discard when the close affordance is tapped a second time', async () => {
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderMobile({ onClose, dirty: true });

      const seal = screen.getByRole('button', { name: /close/i });
      await user.click(seal);
      expect(screen.getByRole('alertdialog', { name: /discard changes/i })).toBeInTheDocument();

      // The repeat gesture belongs to the guard on top, not to the sheet
      // underneath — it used to fall straight through to onClose().
      await user.click(seal);
      expect(onClose).not.toHaveBeenCalled();
      expect(screen.queryByRole('alertdialog', { name: /discard changes/i })).not.toBeInTheDocument();
      expect(screen.getByRole('dialog', { name: 'Title' })).toBeInTheDocument();
    });

    it('renders the guard backdrop over the sheet surface and makes the sheet inert', async () => {
      const user = userEvent.setup();
      renderMobile({ onClose: vi.fn(), dirty: true });

      // With only the sheet up, its own wash sits below the z-50 surface.
      expect(document.querySelector('.modal-ink-wash.z-50')).toBeNull();

      await user.click(screen.getByRole('button', { name: /close/i }));

      // The guard's wash has to clear the sheet's own z-50 surface, otherwise
      // the sheet stays undimmed and fully tappable behind an "alertdialog".
      expect(document.querySelector('.modal-ink-wash.z-50')).not.toBeNull();
      expect(screen.getByRole('dialog', { name: 'Title' }).className)
        .toContain('pointer-events-none');
    });

    it('confirming the guard closes the sheet', async () => {
      const onClose = vi.fn();
      const user = userEvent.setup();
      renderMobile({ onClose, dirty: true });

      await user.click(screen.getByRole('button', { name: /close/i }));
      await user.click(screen.getByRole('button', { name: 'Discard' }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('sticky footer + on-screen keyboard', () => {
    it('renders the footer slot outside the scrolling body', () => {
      renderMobile({ footer: <button type="button">Save it</button> });
      expect(screen.getByRole('button', { name: 'Save it' })).toBeInTheDocument();
    });

    // dvh doesn't shrink for the keyboard, so a bottom-anchored sheet keeps
    // its full height and the keyboard covers the action row.
    it('lifts the mobile sheet above the on-screen keyboard', async () => {
      const listeners = {};
      window.visualViewport = {
        height: 800,
        offsetTop: 0,
        addEventListener: (event, cb) => { listeners[event] = cb; },
        removeEventListener: vi.fn(),
      };
      window.innerHeight = 800;

      renderMobile();
      const dialog = screen.getByRole('dialog', { name: 'Title' });
      expect(dialog.style.bottom).toBe('');

      // Keyboard up: the visual viewport shrinks, the layout viewport doesn't.
      window.visualViewport.height = 460;
      await act(async () => { listeners.resize?.(); });

      expect(dialog.style.bottom).toBe('340px');
      expect(dialog.style.maxHeight).toBe('calc(90dvh - 340px)');

      delete window.visualViewport;
    });
  });
});
