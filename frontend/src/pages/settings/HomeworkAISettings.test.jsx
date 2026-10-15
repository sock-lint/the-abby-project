import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import { buildParent, buildUser } from '../../test/factories';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { setToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import * as api from '../../api';
import SettingsPage from '../SettingsPage';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const DISCONNECTED = { provider: 'default', model: '', has_api_key: false };
const OPENAI = { provider: 'openai', model: 'gpt-5.4-mini', has_api_key: true };

function renderSettings(settings = DISCONNECTED, role = 'parent', handlers = [], ui = <SettingsPage />) {
  server.use(
    ...handlers,
    http.get('*/api/auth/me/', () => HttpResponse.json(
      role === 'parent' ? buildParent({ family: { id: 1, name: 'Test family' } }) : buildUser(),
    )),
    http.get('*/api/homework/ai-settings/', () => HttpResponse.json(settings)),
    http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [] })),
  );
  return renderWithProviders(ui);
}

async function chooseOpenAI(user) {
  await user.selectOptions(await screen.findByLabelText('AI provider'), 'openai');
  await user.type(screen.getByLabelText('API key'), 'synthetic-openai-key');
}

describe('Planning AI settings', () => {
  it('lets a family parent save an OpenAI model and keeps the key out of the confirmed form', async () => {
    const spy = spyHandler('put', /\/api\/homework\/ai-settings\/$/, OPENAI);
    const { user } = renderSettings(DISCONNECTED, 'parent', [spy.handler]);
    await chooseOpenAI(user);
    expect(screen.getByLabelText('API key')).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0]).toEqual({
      url: expect.stringMatching(/\/api\/homework\/ai-settings\/$/), method: 'PUT',
      body: { provider: 'openai', model: 'gpt-5.4-mini', api_key: 'synthetic-openai-key' },
    });
    expect(await screen.findByText('Planning AI settings saved.')).toHaveAttribute('role', 'status');
    expect(screen.getByLabelText('API key')).toHaveValue('');
    expect(screen.getByText(/homework title and description/i)).toBeInTheDocument();
    expect(screen.getByText(/API billing is separate/i)).toBeInTheDocument();
    expect(screen.getByText(/encrypted on the server/i)).toBeInTheDocument();
    expect(JSON.stringify(localStorage)).not.toContain('synthetic-openai-key');
  });

  it('does not display or request parent AI settings for children', async () => {
    const spy = spyHandler('get', /\/api\/homework\/ai-settings\/$/, OPENAI);
    renderSettings(DISCONNECTED, 'child', [spy.handler]);
    await screen.findByText('Username');
    expect(screen.queryByRole('heading', { name: 'Planning AI' })).not.toBeInTheDocument();
    expect(spy.calls).toHaveLength(0);
  });

  it('keeps a saved provider key when only the model changes and supports a custom model ID', async () => {
    const spy = spyHandler('put', /\/api\/homework\/ai-settings\/$/, { ...OPENAI, model: 'custom-model-v1' });
    const { user } = renderSettings(OPENAI, 'parent', [spy.handler]);
    await user.selectOptions(await screen.findByLabelText('Model'), 'custom');
    await user.type(screen.getByLabelText('Custom model ID'), 'custom-model-v1');
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ provider: 'openai', model: 'custom-model-v1' });
    expect(await screen.findByText('Planning AI settings saved.')).toBeInTheDocument();
    expect(screen.getByLabelText('Custom model ID')).toHaveValue('custom-model-v1');
  });

  it('starts disconnected with only OpenAI and Claude choices and requires a new provider key', async () => {
    const spy = spyHandler('put', /\/api\/homework\/ai-settings\/$/, OPENAI);
    const { user } = renderSettings(DISCONNECTED, 'parent', [spy.handler]);
    const provider = await screen.findByLabelText('AI provider');
    expect(provider).toHaveValue('');
    expect(within(provider).getByRole('option', { name: 'Choose a provider' })).toBeDisabled();
    expect(within(provider).getAllByRole('option').filter((option) => !option.disabled)
      .map((option) => option.value)).toEqual(['openai', 'anthropic']);
    expect(screen.getByText('AI planning is off until a parent connects OpenAI or Claude.')).toBeInTheDocument();
    expect(screen.queryByText(/default planner/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('API key')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Model')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save planning AI' })).toBeDisabled();
    await user.selectOptions(provider, 'openai');
    expect(screen.getByLabelText('API key')).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    expect(await screen.findByText('Enter an API key for the selected provider.')).toBeInTheDocument();
    expect(spy.calls).toHaveLength(0);
  });

  it('clears a draft key when the provider changes and requires a new key for Claude', async () => {
    const anthropic = { provider: 'anthropic', model: 'claude-haiku-5-5', has_api_key: true };
    const spy = spyHandler('put', /\/api\/homework\/ai-settings\/$/, anthropic);
    const { user } = renderSettings(OPENAI, 'parent', [spy.handler]);
    await user.type(await screen.findByLabelText('API key'), 'discard-this-key');
    await user.selectOptions(screen.getByLabelText('AI provider'), 'anthropic');
    expect(screen.getByLabelText('API key')).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    expect(await screen.findByText('Enter an API key for the selected provider.')).toBeInTheDocument();
    expect(spy.calls).toHaveLength(0);
    await user.type(screen.getByLabelText('API key'), 'synthetic-anthropic-key');
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({
      provider: 'anthropic', model: 'claude-haiku-5-5', api_key: 'synthetic-anthropic-key',
    });
  });

  it('retains the draft and allows retry after a failed save', async () => {
    let fail = true;
    const spy = spyHandler('put', /\/api\/homework\/ai-settings\/$/, () => fail
      ? HttpResponse.json({ api_key: ['The API key could not be saved.'] }, { status: 400 })
      : OPENAI);
    const { user } = renderSettings(DISCONNECTED, 'parent', [spy.handler]);
    await chooseOpenAI(user);
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The API key could not be saved.');
    expect(screen.queryByText('Planning AI settings saved.')).not.toBeInTheDocument();
    expect(screen.getByLabelText('API key')).toHaveValue('synthetic-openai-key');
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    expect(await screen.findByText('Planning AI settings saved.')).toBeInTheDocument();
    expect(spy.calls).toHaveLength(2);
  });

  it('requires a confirmed settings response before showing success', async () => {
    const spy = spyHandler('put', /\/api\/homework\/ai-settings\/$/, DISCONNECTED);
    const { user } = renderSettings(DISCONNECTED, 'parent', [spy.handler]);
    await chooseOpenAI(user);
    await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save planning AI settings. Try again.');
    expect(screen.queryByText('Planning AI settings saved.')).not.toBeInTheDocument();
    expect(screen.getByLabelText('API key')).toHaveValue('synthetic-openai-key');
  });

  it('recovers a failed load without presenting disconnected settings as saved', async () => {
    let fail = true;
    const { user } = renderSettings(DISCONNECTED, 'parent', [http.get('*/api/homework/ai-settings/', () => fail
      ? HttpResponse.json({ detail: 'Unavailable' }, { status: 503 }) : HttpResponse.json(OPENAI))]);
    const retry = await screen.findByRole('button', { name: 'Retry planning AI settings' });
    expect(screen.queryByLabelText('AI provider')).not.toBeInTheDocument();
    fail = false;
    await user.click(retry);
    expect(await screen.findByLabelText('AI provider')).toHaveValue('openai');
  });

  it('removes the family connection only after confirmation, and can retry a failed removal', async () => {
    let fail = true;
    const spy = spyHandler('delete', /\/api\/homework\/ai-settings\/$/, () => fail
      ? HttpResponse.json({ detail: 'Unavailable' }, { status: 503 }) : DISCONNECTED);
    const { user } = renderSettings(OPENAI, 'parent', [spy.handler]);
    await user.click(await screen.findByRole('button', { name: 'Remove connection' }));
    let confirmation = await screen.findByRole('alertdialog', { name: 'Remove planning AI connection?' });
    expect(spy.calls).toHaveLength(0);
    await user.click(within(confirmation).getByRole('button', { name: 'Remove connection' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not remove/i);
    expect(screen.getByLabelText('AI provider')).toHaveValue('openai');
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Remove connection' }));
    confirmation = await screen.findByRole('alertdialog');
    await user.click(within(confirmation).getByRole('button', { name: 'Remove connection' }));
    expect(await screen.findByText('Planning AI connection removed.')).toBeInTheDocument();
    expect(screen.getByText('AI planning is off until a parent connects OpenAI or Claude.')).toBeInTheDocument();
    expect(screen.queryByLabelText('API key')).not.toBeInTheDocument();
    expect(screen.queryByText(/default planner/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText('AI provider')).toHaveValue('');
    expect(spy.calls).toHaveLength(2);
    expect(spy.calls[1]).toEqual({ url: expect.stringMatching(/\/api\/homework\/ai-settings\/$/), method: 'DELETE', body: null });
  });

  it('prevents overlapping saves and ignores a response after the credential changes', async () => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const mutation = vi.spyOn(api, 'updateHomeworkAISettings');
    const requests = [];
    const { user } = renderSettings(DISCONNECTED, 'parent', [http.put('*/api/homework/ai-settings/', async ({ request }) => {
      requests.push(await request.json());
      await pending;
      return HttpResponse.json(OPENAI);
    })]);
    try {
      await chooseOpenAI(user);
      await user.click(screen.getByRole('button', { name: 'Save planning AI' }));
      expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
      await user.click(screen.getByRole('button', { name: 'Saving…' }));
      await waitFor(() => expect(requests).toHaveLength(1));
      act(() => setToken('synthetic-replacement-credential'));
      await act(async () => { finish(); await mutation.mock.results[0].value; });
      expect(screen.queryByText('Planning AI settings saved.')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('API key')).not.toBeInTheDocument();
    } finally {
      finish();
    }
  });

  it('clears a typed key when the family account changes', async () => {
    function SwitchAccount() {
      const { setUser } = useAuth();
      return <><button onClick={() => setUser(buildParent({ id: 100, family: { id: 2 } }))}>Switch account</button><SettingsPage /></>;
    }
    const { user } = renderSettings(DISCONNECTED, 'parent', [], <SwitchAccount />);
    await chooseOpenAI(user);
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    expect(await screen.findByLabelText('AI provider')).toHaveValue('');
    await user.selectOptions(screen.getByLabelText('AI provider'), 'openai');
    expect(screen.getByLabelText('API key')).toHaveValue('');
  });

  it('clears a draft when a replacement credential rehydrates the same account in one update', async () => {
    function ReplaceCredential() {
      const { setUser } = useAuth();
      return <><button onClick={() => {
        setToken('synthetic-replacement-credential');
        setUser(buildParent({ family: { id: 1, name: 'Test family' } }));
      }}>Replace credential</button><SettingsPage /></>;
    }
    const { user } = renderSettings(DISCONNECTED, 'parent', [], <ReplaceCredential />);
    await chooseOpenAI(user);
    await user.click(screen.getByRole('button', { name: 'Replace credential' }));
    expect(await screen.findByLabelText('AI provider')).toHaveValue('');
    await user.selectOptions(screen.getByLabelText('AI provider'), 'openai');
    expect(screen.getByLabelText('API key')).toHaveValue('');
  });
});
