import { describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ModalBackdrop from './ModalBackdrop.jsx';

const wash = () => document.querySelector('.modal-ink-wash');
const flash = () => document.querySelector('[data-testid="modal-ink-wash-flash"]');

describe('ModalBackdrop', () => {
  it('fires onClick on the wash layer', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ModalBackdrop onClick={onClick} />);
    await user.click(container.querySelector('.modal-ink-wash'));
    expect(onClick).toHaveBeenCalled();
  });

  it('ignores clicks when disabled', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ModalBackdrop onClick={onClick} disabled />);
    await user.click(container.querySelector('.modal-ink-wash'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('accepts a custom zIndex class', () => {
    const { container } = render(<ModalBackdrop onClick={() => {}} zIndex="z-99" />);
    expect(container.innerHTML).toContain('z-99');
  });

  // The disabled-tap feedback used to animate the wash's opacity from 1 to
  // 1.4, which CSS clamps at 1 — a mid-save tap produced no visible change at
  // all. The signal now lives on a second stacked wash that starts at 0, so it
  // has somewhere to move to.
  describe('disabled-tap feedback', () => {
    it('starts with the flash layer invisible and out of the click path', () => {
      render(<ModalBackdrop onClick={() => {}} disabled />);
      expect(flash()).toBeInTheDocument();
      expect(flash()).not.toBe(wash());
      expect(flash().className).toContain('pointer-events-none');
      expect(Number(flash().style.opacity || 0)).toBe(0);
    });

    it('raises the flash layer above 0 when a disabled backdrop is tapped', async () => {
      const user = userEvent.setup();
      render(<ModalBackdrop onClick={() => {}} disabled />);
      await user.click(wash());
      await waitFor(() => {
        expect(Number(flash().style.opacity)).toBeGreaterThan(0);
      });
    });

    it('leaves the flash layer alone when the backdrop can actually close', async () => {
      const user = userEvent.setup();
      render(<ModalBackdrop onClick={() => {}} />);
      await user.click(wash());
      expect(Number(flash().style.opacity || 0)).toBe(0);
    });
  });

  // A drag on the backdrop (or on a short sheet whose own content doesn't
  // scroll) used to scroll the page underneath, and in the installed Android
  // PWA could chain into pull-to-refresh and reload the SPA mid-form.
  describe('body scroll lock', () => {
    it('locks page scroll while mounted and restores it on unmount', () => {
      const { unmount } = render(<ModalBackdrop onClick={() => {}} />);
      expect(document.body.style.overflow).toBe('hidden');
      expect(document.body.style.overscrollBehaviorY).toBe('contain');
      expect(document.documentElement.style.overflow).toBe('hidden');

      unmount();
      expect(document.body.style.overflow).toBe('');
      expect(document.body.style.overscrollBehaviorY).toBe('');
      expect(document.documentElement.style.overflow).toBe('');
    });

    it('keeps the lock while a stacked backdrop is still open', () => {
      const { unmount: unmountOuter } = render(<ModalBackdrop onClick={() => {}} />);
      const { unmount: unmountInner } = render(<ModalBackdrop onClick={() => {}} zIndex="z-50" />);

      unmountInner();
      // The outer sheet is still up — releasing its lock here would let the
      // page scroll behind it.
      expect(document.body.style.overflow).toBe('hidden');

      unmountOuter();
      expect(document.body.style.overflow).toBe('');
    });
  });
});
