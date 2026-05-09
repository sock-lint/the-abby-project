import { afterEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChecklistRail from './ChecklistRail.jsx';
import { server } from '../../../test/server.js';

const FIXTURE_MD = `# Manual Testing — Random & Conditional UI Checklist

Some intro paragraph that should NOT be parsed as a row.

## A. Celebration overlays / modals

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| CelebrationModal (streak milestone) | Unread STREAK_MILESTONE | force_celebration | Full-screen at App boot. |
| CelebrationModal (perfect day) | Unread PERFECT_DAY | force_celebration | Full-screen. Sun icon. |

## B. Toast stacks

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| DropToastStack (common) | Drop with rarity NOT in rare set | force_drop | Top-right slide-in. |
`;

afterEach(() => {
  localStorage.clear();
});

describe('ChecklistRail', () => {
  it('parses sections + rows from the markdown table', async () => {
    server.use(
      http.get('*/api/dev/checklist/', () => HttpResponse.json({ markdown: FIXTURE_MD })),
    );
    render(<ChecklistRail />);

    expect(await screen.findByText('A. Celebration overlays / modals')).toBeInTheDocument();
    expect(screen.getByText('B. Toast stacks')).toBeInTheDocument();
    expect(screen.getByText(/CelebrationModal \(streak milestone\)/)).toBeInTheDocument();
    expect(screen.getByText(/CelebrationModal \(perfect day\)/)).toBeInTheDocument();
    expect(screen.getByText(/DropToastStack \(common\)/)).toBeInTheDocument();

    // 3 rows total → 0/3 progress chip
    expect(screen.getByText(/0 \/ 3/)).toBeInTheDocument();
  });

  it('persists check marks across remount via localStorage', async () => {
    server.use(
      http.get('*/api/dev/checklist/', () => HttpResponse.json({ markdown: FIXTURE_MD })),
    );
    const user = userEvent.setup();
    const { unmount } = render(<ChecklistRail />);

    await screen.findByText(/CelebrationModal \(streak milestone\)/);
    const firstCheckbox = screen.getAllByRole('checkbox')[0];
    await user.click(firstCheckbox);

    await waitFor(() => {
      expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument();
    });

    unmount();

    render(<ChecklistRail />);
    await waitFor(() => {
      expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument();
    });
    // The checked checkbox is still checked.
    expect(screen.getAllByRole('checkbox')[0]).toBeChecked();
  });

  it('Clear button wipes all check marks', async () => {
    server.use(
      http.get('*/api/dev/checklist/', () => HttpResponse.json({ markdown: FIXTURE_MD })),
    );
    const user = userEvent.setup();
    render(<ChecklistRail />);

    await screen.findByText(/CelebrationModal \(streak milestone\)/);
    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    await user.click(checkboxes[1]);

    await waitFor(() => expect(screen.getByText(/2 \/ 3/)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /clear/i }));

    await waitFor(() => expect(screen.getByText(/0 \/ 3/)).toBeInTheDocument());
    for (const cb of screen.getAllByRole('checkbox')) {
      expect(cb).not.toBeChecked();
    }
  });

  it('shows a friendly message when the markdown is empty', async () => {
    server.use(
      http.get('*/api/dev/checklist/', () => HttpResponse.json({ markdown: '' })),
    );
    render(<ChecklistRail />);
    await waitFor(() => {
      expect(screen.getByText(/empty or not bundled/i)).toBeInTheDocument();
    });
  });
});
