import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import SuccessToastProvider from './SuccessToast';
import { useSuccessToast } from '../contexts/SuccessToastContext';
import { TOAST_DURATION_SHORT } from '../constants/timing';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});
vi.mock('../hooks/usePrefersReducedMotion', () => ({ default: () => true }));

function Trigger() {
  const show = useSuccessToast();
  return <button onClick={() => show('Saved your changes')}>Save</button>;
}

describe('SuccessToast', () => {
  afterEach(() => vi.useRealTimers());
  it('expires with reduced motion without depending on an entrance-animation callback', () => {
    vi.useFakeTimers();
    render(<SuccessToastProvider><Trigger /></SuccessToastProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText('Saved your changes')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(TOAST_DURATION_SHORT + 100));
    expect(screen.queryByText('Saved your changes')).not.toBeInTheDocument();
  });
});
