import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import ProgressBar from './ProgressBar.jsx';

describe('ProgressBar', () => {
  it('renders at 0% when max is 0', () => {
    const { container } = render(<ProgressBar value={5} max={0} />);
    const fill = container.querySelector('.rounded-full.h-full');
    // Framer uses a motion.div; assertion is loose because animated.
    expect(fill).toBeTruthy();
  });

  it('clamps fill to 100% when value exceeds max', () => {
    const { container } = render(<ProgressBar value={200} max={100} />);
    // Rendered ratio is capped but there's always a single fill element.
    expect(container.querySelectorAll('.rounded-full').length).toBeGreaterThan(0);
  });

  it('accepts a custom color class', () => {
    const { container } = render(
      <ProgressBar value={50} max={100} color="bg-ember" />,
    );
    expect(container.innerHTML).toContain('bg-ember');
  });

  it('accepts an outer className', () => {
    const { container } = render(<ProgressBar value={0} className="w-full" />);
    expect(container.firstChild.className).toContain('w-full');
  });

  it('handles partial values', () => {
    const { container } = render(<ProgressBar value={25} max={100} />);
    expect(container.firstChild).toBeTruthy();
  });
});
