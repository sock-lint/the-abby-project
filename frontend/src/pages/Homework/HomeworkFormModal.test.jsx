import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/render.jsx';
import HomeworkFormModal from './HomeworkFormModal.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('HomeworkFormModal', () => {
  it('routes the empty-children Manage hint through react-router', () => {
    // Regression: this was a raw <a href="/manage">, which in the installed
    // PWA tears the app down and re-boots it, losing everything typed into
    // the open form. A router <Link> keeps the SPA alive.
    renderWithProviders(
      <HomeworkFormModal
        isParent
        childrenList={[]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
      { withAuth: false },
    );

    const link = screen.getByRole('link', { name: /manage/i });
    expect(link).toHaveAttribute('href', '/manage');
    // react-router's Link intercepts the click; a raw anchor would not.
    const clicked = new MouseEvent('click', { bubbles: true, cancelable: true });
    link.dispatchEvent(clicked);
    expect(clicked.defaultPrevented).toBe(true);
  });
});
