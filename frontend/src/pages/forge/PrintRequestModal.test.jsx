import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import PrintRequestModal from './PrintRequestModal';

const URL_UNDER_TEST = 'https://makerworld.com/en/models/1';

describe('PrintRequestModal', () => {
  it('previews the link on blur and fills the title from the scrape', async () => {
    server.use(
      http.post('*/api/print-requests/preview/', () =>
        HttpResponse.json({
          title: 'Articulated Dragon',
          thumbnail_url: 'https://cdn.example/dragon.png',
          author: 'someone',
          source_kind: 'makerworld',
          error: null,
        }),
      ),
    );
    const { user } = renderWithProviders(<PrintRequestModal onClose={() => {}} />);

    await user.type(screen.getByLabelText(/link to the model/i), URL_UNDER_TEST);
    await user.tab();

    expect(await screen.findByText('Articulated Dragon')).toBeInTheDocument();
    expect(screen.getByText(/by someone/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/what is it/i)).toHaveValue('Articulated Dragon');
    });
  });

  it('renders a failed preview as a soft hint, not a blocker', async () => {
    server.use(
      http.post('*/api/print-requests/preview/', () =>
        HttpResponse.json({
          title: '', thumbnail_url: '', author: '',
          source_kind: 'other_url', error: 'timed out',
        }),
      ),
    );
    const { user } = renderWithProviders(<PrintRequestModal onClose={() => {}} />);

    await user.type(screen.getByLabelText(/link to the model/i), URL_UNDER_TEST);
    await user.tab();

    expect(await screen.findByText(/Couldn’t read the page/i)).toBeInTheDocument();
    // Still submittable — the whole point of the soft failure.
    await user.type(screen.getByLabelText(/colour/i), 'green');
    await user.type(screen.getByLabelText(/why do you want it/i), 'because');
    expect(screen.getByRole('button', { name: /send request/i })).not.toBeDisabled();
  });

  it('POSTs the request as JSON when the child pasted a link', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/$/, { id: 9 });
    server.use(spy.handler);

    const { user } = renderWithProviders(<PrintRequestModal onClose={() => {}} />);

    await user.type(screen.getByLabelText(/link to the model/i), URL_UNDER_TEST);
    await user.type(screen.getByLabelText(/what is it/i), 'Dragon');
    await user.type(screen.getByLabelText(/colour/i), 'green');
    await user.type(screen.getByLabelText(/why do you want it/i), 'birthday present');
    await user.click(screen.getByRole('button', { name: /send request/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-requests\/$/);
    expect(spy.calls[0].body).toEqual({
      title: 'Dragon',
      source_url: URL_UNDER_TEST,
      color: 'green',
      reason: 'birthday present',
      needed_by: null,
    });
  });

  it('sends a needed-by date when a quick chip is tapped', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/$/, { id: 10 });
    server.use(spy.handler);

    const { user } = renderWithProviders(<PrintRequestModal onClose={() => {}} />);

    await user.type(screen.getByLabelText(/link to the model/i), URL_UNDER_TEST);
    await user.type(screen.getByLabelText(/colour/i), 'red');
    await user.type(screen.getByLabelText(/why do you want it/i), 'school project');
    await user.click(screen.getByRole('button', { name: 'Tomorrow' }));
    await user.click(screen.getByRole('button', { name: /send request/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body.needed_by).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('switches to multipart when the child uploads a model file', async () => {
    const calls = [];
    server.use(
      http.post('*/api/print-requests/', async ({ request }) => {
        const form = await request.formData();
        calls.push({
          color: form.get('color'),
          reason: form.get('reason'),
          // The title defaults to the file's own name when the child didn't
          // type one — jsdom's FormData drops File.name, so assert through
          // the field the modal actually derives from it.
          title: form.get('title'),
          hasFile: Boolean(form.get('model_file')),
        });
        return HttpResponse.json({ id: 11 }, { status: 201 });
      }),
    );

    const { user } = renderWithProviders(<PrintRequestModal onClose={() => {}} />);
    await user.click(screen.getByRole('button', { name: /upload/i }));

    const file = new File(['solid'], 'dragon.stl', { type: 'model/stl' });
    await user.upload(screen.getByLabelText(/model file/i), file);
    await user.type(screen.getByLabelText(/colour/i), 'grey');
    await user.type(screen.getByLabelText(/why do you want it/i), 'i made it');
    await user.click(screen.getByRole('button', { name: /send request/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({
      color: 'grey', reason: 'i made it', title: 'dragon.stl', hasFile: true,
    });
  });
});
