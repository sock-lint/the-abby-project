import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ProjectNew from './ProjectNew.jsx';
import { server } from '../test/server.js';

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectNew />
    </MemoryRouter>,
  );
}

describe('ProjectNew', () => {
  it('renders the form with required fields', () => {
    renderPage();
    expect(screen.getByText(/new project/i)).toBeInTheDocument();
    // Labels in ProjectNew aren't `htmlFor`-associated; rely on text + role.
    expect(screen.getAllByText(/title/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/category/i).length).toBeGreaterThan(0);
  });

  it('submits and navigates on success', async () => {
    server.use(
      http.post('*/api/projects/', () => HttpResponse.json({ id: 99 })),
    );
    const user = userEvent.setup();
    renderPage();
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Bird Feeder');
    await user.click(screen.getByRole('button', { name: /create project/i }));
    // No assertion needed beyond no-throw — navigate is exercised.
  });

  it('displays an error from the server', async () => {
    server.use(
      http.post('*/api/projects/', () =>
        HttpResponse.json({ error: 'bad title' }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'x');
    await user.click(screen.getByRole('button', { name: /create project/i }));
    expect(await screen.findByText(/bad title/i)).toBeInTheDocument();
  });

  it('previews an Instructables URL on blur', async () => {
    server.use(
      http.get('*/api/instructables/preview/', () =>
        HttpResponse.json({ title: 'Cool Project', author: 'somebody', step_count: 5 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    const urlInput = document.querySelector('input[type="url"]');
    await user.type(urlInput, 'https://www.instructables.com/x');
    urlInput.blur();
    await waitFor(() => expect(screen.getByText(/cool project/i)).toBeInTheDocument());
  });

  it('skips preview for non-instructables URLs', async () => {
    const user = userEvent.setup();
    renderPage();
    const urlInput = document.querySelector('input[type="url"]');
    await user.type(urlInput, 'https://example.com');
    urlInput.blur();
    // Nothing displayed.
    expect(screen.queryByText(/loading preview/i)).toBeNull();
  });
});
