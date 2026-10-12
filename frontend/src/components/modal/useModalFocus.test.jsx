import { useRef } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import useModalFocus from './useModalFocus';

function Dialog({ suspended, onEscape }) {
  const dialogRef = useRef(null);
  useModalFocus({ dialogRef, suspended, onEscape });
  return <div ref={dialogRef} role="dialog" tabIndex={-1}><button>Choose file</button></div>;
}

describe('external picker focus', () => {
  it('lets an external picker own focus and Escape, then resumes the sheet', () => {
    const onEscape = vi.fn();
    const { rerender } = render(<><button>External picker</button><Dialog suspended={false} onEscape={onEscape} /></>);
    const choose = screen.getByRole('button', { name: 'Choose file' });
    const external = screen.getByRole('button', { name: 'External picker' });
    expect(choose).toHaveFocus();
    rerender(<><button>External picker</button><Dialog suspended onEscape={onEscape} /></>);
    act(() => external.focus());
    expect(external).toHaveFocus();
    fireEvent.keyDown(external, { key: 'Escape' });
    expect(onEscape).not.toHaveBeenCalled();
    rerender(<><button>External picker</button><Dialog suspended={false} onEscape={onEscape} /></>);
    expect(choose).toHaveFocus();
    act(() => external.focus());
    expect(choose).toHaveFocus();
    fireEvent.keyDown(choose, { key: 'Escape' });
    expect(onEscape).toHaveBeenCalledOnce();
  });
});
