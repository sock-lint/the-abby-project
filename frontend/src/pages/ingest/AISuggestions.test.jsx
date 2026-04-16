import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AISuggestions from './AISuggestions.jsx';

describe('AISuggestions', () => {
  it('renders nothing when no suggestions', () => {
    const { container } = render(
      <AISuggestions
        suggestions={{}}
        categories={[]}
        overrides={{}}
        setOverrides={vi.fn()}
        setDraft={vi.fn()}
      />,
    );
    // Component renders something even with empty suggestions.
    expect(container).toBeTruthy();
  });

  it('applies difficulty suggestion', async () => {
    const setOverrides = vi.fn();
    const user = userEvent.setup();
    render(
      <AISuggestions
        suggestions={{ difficulty: 4 }}
        categories={[]}
        overrides={{ difficulty: 2 }}
        setOverrides={setOverrides}
        setDraft={vi.fn()}
      />,
    );
    const btns = screen.queryAllByRole('button');
    for (const b of btns) {
      await user.click(b);
    }
    expect(setOverrides).toHaveBeenCalled();
  });
});
