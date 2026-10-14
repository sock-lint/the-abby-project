import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, fireEvent, renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent } from '../test/factories';
import { PwaStatusProvider } from './PwaStatusProvider';
import { usePwaStatus } from './pwaStatus.context';
import ProjectNew from '../pages/ProjectNew';
import ProjectIngest from '../pages/ProjectIngest';

const registration = vi.hoisted(() => ({ callbacks: null, update: vi.fn() }));
vi.mock('./registerPromptWorker', () => ({ registerPromptWorker: (callbacks) => {
  registration.callbacks = callbacks;
  return { update: registration.update, dispose: () => {} };
} }));

function Apply() {
  const { applyUpdate, updateBlocked } = usePwaStatus();
  return <button onClick={applyUpdate}>Apply update {updateBlocked ? 'blocked' : 'available'}</button>;
}

beforeEach(() => {
  registration.callbacks = null;
  registration.update.mockReset();
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
});

describe('Manual page work protects updates', () => {
  it('keeps the new-project form intact without submitting it when an update is requested', async () => {
    const create = spyHandler('post', '*/api/projects/', { id: 42 });
    server.use(create.handler);
    renderWithProviders(<PwaStatusProvider><Apply /><ProjectNew /></PwaStatusProvider>);
    const title = await screen.findByRole('textbox', { name: 'Title' });
    await waitFor(() => expect(registration.callbacks).not.toBeNull());
    act(() => registration.callbacks.onNeedRefresh());
    fireEvent.change(title, { target: { value: 'Keep my unfinished project' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply update blocked' }));
    expect(registration.update).not.toHaveBeenCalled();
    expect(create.calls).toHaveLength(0);
    expect(title).toHaveValue('Keep my unfinished project');
  });

  it('keeps an unsubmitted import source intact without creating an ingestion job', async () => {
    const start = spyHandler('post', '*/api/projects/ingest/', { id: 'unstarted-job' });
    server.use(start.handler);
    renderWithProviders(<PwaStatusProvider><Apply /><ProjectIngest /></PwaStatusProvider>);
    const source = await screen.findByRole('textbox', { name: 'Tutorial URL' });
    await waitFor(() => expect(registration.callbacks).not.toBeNull());
    act(() => registration.callbacks.onNeedRefresh());
    fireEvent.change(source, { target: { value: 'https://example.com/tutorial' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply update blocked' }));
    expect(registration.update).not.toHaveBeenCalled();
    expect(start.calls).toHaveLength(0);
    expect(source).toHaveValue('https://example.com/tutorial');
  });
});
