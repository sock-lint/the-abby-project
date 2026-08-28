import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import ScrollToTop from './ScrollToTop';

function renderWithRoutes(initialPath = '/a') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ScrollToTop />
      <Routes>
        <Route
          path="/a"
          element={
            <>
              <Link to="/b">go to b</Link>
              <Link to="/a?tab=second">switch tab</Link>
            </>
          }
        />
        <Route path="/b" element={<div>page b</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ScrollToTop', () => {
  it('resets window scroll when the pathname changes', async () => {
    const spy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const user = userEvent.setup();
    renderWithRoutes();
    spy.mockClear();

    await user.click(screen.getByText('go to b'));

    expect(screen.getByText('page b')).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith({ top: 0, left: 0, behavior: 'instant' });
    spy.mockRestore();
  });

  it('does not fire on a search-param-only change — intra-hub tab switches stay ChapterHub’s job', async () => {
    const spy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    const user = userEvent.setup();
    renderWithRoutes();
    spy.mockClear();

    await user.click(screen.getByText('switch tab'));

    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
