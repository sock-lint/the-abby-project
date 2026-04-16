import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ModalBackdrop from './ModalBackdrop.jsx';

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
});
