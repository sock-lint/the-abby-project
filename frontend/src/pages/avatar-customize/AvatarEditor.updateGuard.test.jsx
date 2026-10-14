import { useLayoutEffect, useMemo } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, userEvent, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { setToken } from '../../api/client';
import { PwaStatusProvider } from '../../pwa/PwaStatusProvider';
import { PwaStatusContext, usePwaStatus } from '../../pwa/pwaStatus.context';
import AvatarEditor from './AvatarEditor';
import { resolveAvatarCatalog } from './catalog';
import { archerConfiguration, syntheticCatalog } from './catalog.fixtures';
import { resetAvatarDrafts } from './draftStore';

const worker = vi.hoisted(() => ({ callbacks: null, update: vi.fn(), guard: null, attempts: [] }));
vi.mock('../../pwa/registerPromptWorker', () => ({ registerPromptWorker: (callbacks) => {
  worker.callbacks = callbacks;
  return { update: worker.update, dispose: () => {} };
} }));
vi.mock('../../components/avatar/AvatarPreview', () => ({ default: () => <div role="img" aria-label="Synthetic avatar" /> }));

const credential = 'synthetic-avatar-update-session';
const catalog = resolveAvatarCatalog({ ...syntheticCatalog, avatars: [syntheticCatalog.avatars[0]] });

function RegistryAudit({ children }) {
  const status = usePwaStatus();
  const registerUpdateGuard = useMemo(() => vi.fn(status.registerUpdateGuard), [status.registerUpdateGuard]);
  useLayoutEffect(() => { worker.guard = registerUpdateGuard; }, [registerUpdateGuard]);
  // Forward the exact calls to the real provider while inspecting the public
  // registry boundary. The provider still owns protection and activation.
  return <PwaStatusContext.Provider value={{ ...status, registerUpdateGuard }}>{children}</PwaStatusContext.Provider>;
}

function UpdateAttempt() {
  const { updateBlocked, applyUpdate } = usePwaStatus();
  return <>
    <output aria-label="App update protection">{updateBlocked ? 'Blocked' : 'Ready'}</output>
    <button onClick={() => worker.attempts.push(applyUpdate())}>Apply app update</button>
  </>;
}

async function openEditor() {
  const view = renderWithProviders(<PwaStatusProvider><RegistryAudit>
    <UpdateAttempt />
    <AvatarEditor catalog={catalog} initialConfiguration={archerConfiguration} accountId={41} credential={credential} />
  </RegistryAudit></PwaStatusProvider>, { withAuth: false });
  await waitFor(() => expect(worker.callbacks).not.toBeNull());
  act(() => worker.callbacks.onNeedRefresh());
  expect(screen.getByLabelText('App update protection')).toHaveTextContent('Ready');
  return view;
}

async function blockedUpdate(user) {
  await user.click(screen.getByRole('button', { name: 'Apply app update' }));
  expect(worker.attempts.at(-1)).toBe(false);
  expect(worker.update).not.toHaveBeenCalled();
  expect(screen.getByLabelText('App update protection')).toHaveTextContent('Blocked');
}

async function availableUpdate(user) {
  await waitFor(() => expect(screen.getByLabelText('App update protection')).toHaveTextContent('Ready'));
  await user.click(screen.getByRole('button', { name: 'Apply app update' }));
  expect(worker.attempts.at(-1)).toBe(true);
  expect(worker.update).toHaveBeenCalledOnce();
}

beforeEach(() => {
  resetAvatarDrafts();setToken(credential);
  worker.callbacks = null;worker.guard = null;worker.attempts = [];
  // A synthetic waiting worker lets the real provider attempt activation
  // without installing a worker or reloading this DOM test.
  worker.update.mockReset().mockReturnValue(false);
});

describe('avatar editor app-update protection', () => {
  it('blocks activation for an unsaved look, records only opaque IDs/booleans and permits an update after Undo', async () => {
    const user = userEvent.setup();
    const save = spyHandler('post', /\/api\/character\/avatar\/configuration\/$/, {});server.use(save.handler);
    await openEditor();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await blockedUpdate(user);
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    expect(save.calls).toHaveLength(0);
    expect(worker.guard).toHaveBeenCalled();
    for (const call of worker.guard.mock.calls) {
      expect(call).toHaveLength(2);
      expect(typeof call[0]).toBe('string');expect(typeof call[1]).toBe('boolean');
    }
    const registryCalls = JSON.stringify(worker.guard.mock.calls);
    for (const privateValue of [credential, 'bow-greenhorn', 'avatar_configuration', 'appearance', 'accessories']) expect(registryCalls).not.toContain(privateValue);
    await user.click(screen.getByRole('button', { name: 'Undo changes' }));
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('none');
    await availableUpdate(user);
  });

  it('blocks activation throughout a pending save and permits it after a complete server receipt', async () => {
    const user = userEvent.setup();
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const configuration = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, left_hand: 'bow-greenhorn' } };
    const requests = [];
    server.use(http.post('*/api/character/avatar/configuration/', async ({ request }) => {
      requests.push(await request.json());
      await pending;return HttpResponse.json({ avatar_configuration: configuration });
    }));
    await openEditor();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));
    try {
      await waitFor(() => expect(requests).toHaveLength(1));
      expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
      await blockedUpdate(user);
    } finally { await act(async () => { finish(); await pending; }); }
    expect(await screen.findByText('Avatar saved.')).toBeInTheDocument();
    expect(requests[0]).toEqual({ avatar_configuration: configuration });
    await availableUpdate(user);
  });

  it('keeps a failed save protected until the owner explicitly restores the saved look', async () => {
    const user = userEvent.setup();
    server.use(http.post('*/api/character/avatar/configuration/', () => HttpResponse.json({ error: 'Synthetic save unavailable.' }, { status: 503 })));
    await openEditor();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic save unavailable.');
    await blockedUpdate(user);
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Undo changes' }));
    await availableUpdate(user);
  });
});
