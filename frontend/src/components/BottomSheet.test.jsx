import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
});
