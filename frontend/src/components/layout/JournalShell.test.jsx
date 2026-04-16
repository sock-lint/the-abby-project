import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import JournalShell from './JournalShell.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

function renderShell({ route = '/', element }) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <Routes>
          <Route element={<JournalShell />}>
            <Route path="/" element={element || <div>home</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('JournalShell', () => {
  it('renders nav + outlet content', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    renderShell({ element: <div>page-body</div> });
    await waitFor(() => expect(screen.getByText('page-body')).toBeInTheDocument());
    // Chapter sidebar labels are rendered regardless of auth state.
    expect(screen.getAllByText('Today').length).toBeGreaterThan(0);
  });
});
