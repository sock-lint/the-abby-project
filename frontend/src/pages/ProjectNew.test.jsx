import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/render';
import { buildParent } from '../test/factories';
import ProjectNew from './ProjectNew.jsx';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';

async function renderPage() {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
  const view = renderWithProviders(<ProjectNew />);
  await screen.findByLabelText('Title');
  return view;
}

describe('ProjectNew', () => {
  it('renders the form with required fields', async () => {
    await renderPage();
    // The journal calls these "ventures" everywhere else — the page the
    // "New project" button opens says the same word.
    expect(screen.getByRole('heading', { name: /new project/i })).toBeInTheDocument();
    // Labels in ProjectNew aren't `htmlFor`-associated; rely on text + role.
    expect(screen.getAllByText(/title/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/category/i).length).toBeGreaterThan(0);
  });

  it('submits and navigates on success', async () => {
    const create = spyHandler('post', '*/api/projects/', { id: 99 });
    server.use(create.handler);
    const user = userEvent.setup();
    await renderPage();
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Bird Feeder');
    await user.click(screen.getByRole('button', { name: /create project/i }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/projects\/$/);
    expect(create.calls[0].body).toEqual({
      title: 'Bird Feeder', description: '', instructables_url: null, difficulty: 2,
      category_id: null, bonus_amount: '0', materials_budget: '0', due_date: null,
      payment_kind: 'required', assigned_to_id: null, hourly_rate_override: null,
      parent_notes: '',
    });
  });

  it('displays an error from the server', async () => {
    server.use(
      http.post('*/api/projects/', () =>
        HttpResponse.json({ error: 'bad title' }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    await renderPage();
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
    await renderPage();
    const urlInput = document.querySelector('input[type="url"]');
    await user.type(urlInput, 'https://www.instructables.com/x');
    urlInput.blur();
    await waitFor(() => expect(screen.getByText(/cool project/i)).toBeInTheDocument());
  });

  it('skips preview for non-instructables URLs', async () => {
    const user = userEvent.setup();
    await renderPage();
    const urlInput = document.querySelector('input[type="url"]');
    await user.type(urlInput, 'https://example.com');
    urlInput.blur();
    // Nothing displayed.
    expect(screen.queryByText(/loading preview/i)).toBeNull();
  });

  it('preserves a title typed while the tutorial preview is loading', async () => {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const previewStarted = vi.fn();
    server.use(http.get('*/api/instructables/preview/', async () => {
      previewStarted();
      await gate;
      return HttpResponse.json({ title: 'Tutorial title', author: 'Maker' });
    }));
    const user = userEvent.setup();
    await renderPage();
    await user.type(screen.getByRole('textbox', { name: /instructables url/i }), 'https://www.instructables.com/feeder');
    await user.click(screen.getByRole('textbox', { name: /^title$/i }));
    await waitFor(() => expect(previewStarted).toHaveBeenCalledOnce());
    await user.type(screen.getByRole('textbox', { name: /^title$/i }), 'My custom title');
    release();
    expect(await screen.findByText('Tutorial title')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /^title$/i })).toHaveValue('My custom title');
  });

  it('ignores a preview for an obsolete URL even when its response arrives last', async () => {
    let releaseOld;
    const oldGate = new Promise(resolve => { releaseOld = resolve; });
    const oldStarted = vi.fn();
    server.use(http.get('*/api/instructables/preview/', async ({ request }) => {
      if (new URL(request.url).searchParams.get('url').endsWith('/old')) {
        oldStarted();
        await oldGate;
        return HttpResponse.json({ title: 'Old tutorial', author: 'Old author' });
      }
      return HttpResponse.json({ title: 'Current tutorial', author: 'Current author' });
    }));
    const user = userEvent.setup();
    await renderPage();
    const url = screen.getByRole('textbox', { name: /instructables url/i });
    await user.type(url, 'https://www.instructables.com/old');
    await user.tab();
    await waitFor(() => expect(oldStarted).toHaveBeenCalledOnce());
    await user.clear(url);
    await user.type(url, 'https://www.instructables.com/current');
    await user.tab();
    expect(await screen.findByText('Current tutorial')).toBeInTheDocument();
    // The transport has no abort option; finish the old response so this test
    // exercises the obsolete-response guard rather than leaving it pending.
    const oldFinished = new Promise(resolve => {
      const onResponse = ({ request }) => {
        if (new URL(request.url).searchParams.get('url')?.endsWith('/old')) {
          server.events.removeListener('response:mocked', onResponse);
          resolve();
        }
      };
      server.events.on('response:mocked', onResponse);
    });
    await act(async () => { releaseOld(); await oldFinished; });
    expect(screen.queryByText('Old tutorial')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /^title$/i })).toHaveValue('Current tutorial');
    expect(screen.getByText(/Current author/)).toBeInTheDocument();
  });
});
