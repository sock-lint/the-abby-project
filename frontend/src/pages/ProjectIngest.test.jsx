import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import ProjectIngest from './ProjectIngest.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { buildParent } from '../test/factories.js';
import { spyHandler } from '../test/spy.js';
import { DEFAULT_OVERRIDES, ingestDraftKey, readIngestDraft, storeIngestDraft } from './ingest/ingestDraft';
import { STORAGE_KEYS } from '../constants/storage';
import { useSpace } from '../hooks/useSpace';

vi.mock('../hooks/useSpace', () => ({ useSpace: vi.fn() }));

beforeEach(() => useSpace.mockReturnValue({ isParentAccount: true, isPersonalSpace: false }));

vi.mock('../components/GoogleDrivePickerButton', () => ({
  default: ({ onPick, children, disabled, pdfOnly }) => (
    <button type="button" disabled={disabled} data-pdf-only={pdfOnly} onClick={() => onPick({
      file_id: 'school-pdf-1', access_token: 'synthetic-drive-token', resource_key: 'synthetic-resource-key',
    })}>{children || 'Choose from Google Drive'}</button>
  ),
}));

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(parent = buildParent()) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parent)));
  return renderWithProviders(
    <Routes>
      <Route path="/quests/ventures/ingest" element={<ProjectIngest />} />
      <Route path="/quests/ventures/:id" element={<p>Created project</p>} />
      <Route path="/quests" element={<p>Projects list</p>} />
    </Routes>,
    { route: '/quests/ventures/ingest' },
  );
}

const plan = { title: 'Bird feeder', description: 'Build it together.', milestones: [], steps: [], materials: [], resources: [] };
const readyJob = { id: 'job-3', status: 'ready', result_json: plan };

function keepDraft(changes = {}, userId = 99) {
  storeIngestDraft(userId, {
    jobId: 'job-3', draft: plan, overrides: DEFAULT_OVERRIDES,
    sourceTab: 'url', url: 'https://example.com/tutorial', pendingCommit: false, ...changes,
  });
}

describe('ProjectIngest', () => {
  it('imports for a parent’s personal space without exposing or replaying a saved cash bonus', async () => {
    useSpace.mockReturnValue({ isParentAccount: true, isPersonalSpace: true });
    keepDraft({ overrides: { ...DEFAULT_OVERRIDES, bonus_amount: '25', materials_budget: '12' } });
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', { id: 44 });
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)), commit.handler);
    const { user } = renderPage(buildParent({ id: 99 }));
    await screen.findByRole('button', { name: /create project/i });
    expect(screen.queryByRole('spinbutton', { name: 'Bonus ($)' })).not.toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /materials budget/i })).toHaveValue(12);
    await user.click(screen.getByRole('button', { name: /create project/i }));
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(commit.calls).toHaveLength(1);
    expect(commit.calls[0]).toMatchObject({ method: 'POST', body: { bonus_amount: '0', materials_budget: '12' } });
    expect(commit.calls[0].url).toMatch(/\/api\/projects\/ingest\/job-3\/commit\/$/);
    expect(commit.calls[0].body).not.toHaveProperty('assigned_to_id');
    expect(readIngestDraft(99)).toBeNull();
  });

  it('starts a selected Drive PDF through the normal review flow without saving its token', async () => {
    const start = spyHandler('post', '*/api/projects/ingest/google-drive/', readyJob);
    const ordinaryStart = spyHandler('post', '*/api/projects/ingest/', {});
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', {});
    server.use(start.handler, ordinaryStart.handler, commit.handler,
      http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)));
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /^pdf$/i }));
    const drive = screen.getByRole('button', { name: /import pdf from google drive/i });
    expect(drive).toHaveAttribute('data-pdf-only', 'true');
    const disclosure = screen.getByText(/up to 12,000 characters of extracted text/i);
    await waitFor(() => expect(disclosure).toBeVisible());
    expect(disclosure).toHaveTextContent('Anthropic (Claude)');
    expect(disclosure).toHaveTextContent('Import PDF from Google Drive');
    expect(screen.getByRole('link', { name: 'Privacy details' })).toHaveAttribute('href', '/privacy/#ai');
    expect(start.calls).toHaveLength(0);
    await user.click(drive);
    await screen.findByRole('button', { name: /create project/i });
    expect(start.calls).toHaveLength(1);
    expect(start.calls[0].body).toEqual({ file_id: 'school-pdf-1', access_token: 'synthetic-drive-token', resource_key: 'synthetic-resource-key' });
    expect(ordinaryStart.calls).toHaveLength(0);
    expect(commit.calls).toHaveLength(0);
    expect(readIngestDraft(99).jobId).toBe('job-3');
    expect(localStorage.getItem(ingestDraftKey(99))).not.toContain('synthetic-drive-token');
    expect(document.body.textContent).not.toContain('synthetic-drive-token');
  });

  it('keeps the PDF source form usable when Google denies file access', async () => {
    const start = spyHandler('post', '*/api/projects/ingest/google-drive/',
      HttpResponse.json({ error: 'Google Drive could not open this file. Choose it again and allow access.' }, { status: 400 }));
    server.use(start.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /^pdf$/i }));
    await user.click(screen.getByRole('button', { name: /import pdf from google drive/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Google Drive could not open this file');
    expect(start.calls).toHaveLength(1);
    expect(screen.getByLabelText('PDF Tutorial')).toBeInTheDocument();
    expect(readIngestDraft(99)).toBeNull();
  });
  it('renders the source step with URL/PDF tabs', async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getAllByText((t) => /url|pdf|source|ingest|import/i.test(t)).length,
      ).toBeGreaterThan(0),
    );
  });

  it('opens exactly one ingestion job however many times Parse Source is tapped', async () => {
    // Each job runs the paid LLM enrichment pipeline server-side, so a
    // double-tap during the in-flight POST must not queue a second one.
    let starts = 0;
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    server.use(
      http.post('*/api/projects/ingest/', async () => {
        starts += 1;
        await gate;
        return HttpResponse.json({ id: 3, status: 'pending' }, { status: 201 });
      }),
      http.get('*/api/projects/ingest/3/', () =>
        HttpResponse.json({ id: 3, status: 'pending' }),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await user.type(
      await screen.findByRole('textbox', { name: /tutorial url/i }),
      'https://www.instructables.com/thing',
    );
    const start = screen.getByRole('button', { name: /parse source/i });
    await user.click(start);

    // Button flips to its in-flight state and stops accepting taps.
    const busy = await screen.findByRole('button', { name: /reading/i });
    expect(busy).toBeDisabled();
    await user.click(busy);

    release();
    await waitFor(() => expect(screen.getByText(/reading the steps/i)).toBeInTheDocument());
    expect(starts).toBe(1);
  });

  it('checks the existing import after a transient poll failure without starting another job', async () => {
    const start = spyHandler('post', '*/api/projects/ingest/', { id: 'job-3', status: 'pending' });
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', () =>
      checks.calls.length === 1 ? HttpResponse.json({ error: 'Connection interrupted' }, { status: 503 }) : readyJob,
    );
    server.use(start.handler, checks.handler);
    const { user } = renderPage();
    await user.type(await screen.findByRole('textbox', { name: /tutorial url/i }), 'https://example.com/tutorial');
    await user.click(screen.getByRole('button', { name: /parse source/i }));
    await user.click(await screen.findByRole('button', { name: /check import/i }));
    expect(await screen.findByDisplayValue('Bird feeder')).toBeInTheDocument();
    expect(start.calls).toHaveLength(1);
    expect(start.calls[0].body).toEqual({ source_type: 'url', source_url: 'https://example.com/tutorial' });
    expect(start.calls[0].url).toMatch(/\/api\/projects\/ingest\/$/);
    expect(checks.calls).toHaveLength(2);
  });

  it('keeps local plan edits and overrides across navigation before autosave finishes', async () => {
    keepDraft();
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', readyJob);
    const start = spyHandler('post', '*/api/projects/ingest/', {});
    server.use(checks.handler, start.handler);
    const first = renderPage();
    const title = await screen.findByRole('textbox', { name: /^title$/i });
    await first.user.clear(title);
    await first.user.type(title, 'Our custom feeder');
    await first.user.clear(screen.getByRole('spinbutton', { name: /materials budget/i }));
    await first.user.type(screen.getByRole('spinbutton', { name: /materials budget/i }), '25');
    first.unmount();
    renderPage();
    expect(await screen.findByDisplayValue('Our custom feeder')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /materials budget/i })).toHaveValue(25);
    expect(screen.getByText(/unfinished import was restored/i)).toBeInTheDocument();
    expect(checks.calls).toHaveLength(2);
    expect(start.calls).toHaveLength(0);
  });

  it('autosaves edited staging data while keeping project creation explicit', async () => {
    keepDraft();
    const save = spyHandler('patch', '*/api/projects/ingest/job-3/', {});
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', { id: 44 });
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)), save.handler, commit.handler);
    const { user } = renderPage();
    const title = await screen.findByRole('textbox', { name: /^title$/i });
    await user.clear(title);
    await user.type(title, 'Edited feeder');
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ result_json: { ...plan, title: 'Edited feeder' } });
    expect(save.calls[0].url).toMatch(/\/api\/projects\/ingest\/job-3\/$/);
    expect(screen.getByText(/edited plan is saved with this import/i)).toBeInTheDocument();
    expect(commit.calls).toHaveLength(0);
  });

  it('creates the project with saved overrides and clears its device draft', async () => {
    keepDraft({ overrides: { ...DEFAULT_OVERRIDES, bonus_amount: '7', materials_budget: '25', difficulty: 4 } });
    const save = spyHandler('patch', '*/api/projects/ingest/job-3/', {});
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', { id: 44 });
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)), save.handler, commit.handler);
    const { user } = renderPage();
    await screen.findByRole('button', { name: /create project/i });
    expect(screen.getByRole('spinbutton', { name: 'Bonus ($)' })).toHaveValue(7);
    await user.click(screen.getByRole('button', { name: /create project/i }));
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(save.calls).toHaveLength(1);
    expect(save.calls[0].body).toEqual({ result_json: plan });
    expect(commit.calls).toHaveLength(1);
    expect(commit.calls[0].url).toMatch(/\/api\/projects\/ingest\/job-3\/commit\/$/);
    expect(commit.calls[0].body).toEqual({ ...plan, category_id: null, difficulty: 4, bonus_amount: '7', materials_budget: '25', due_date: null });
    expect(readIngestDraft(99)).toBeNull();
  });

  it('opens the existing project when a creation staging save conflicts with another tab’s commit', async () => {
    keepDraft();
    let committed = false;
    const save = spyHandler('patch', '*/api/projects/ingest/job-3/', () => {
      committed = true;
      return HttpResponse.json({ error: 'Job already committed' }, { status: 409 });
    });
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', () => committed
      ? { ...readyJob, status: 'committed', project: 44 } : readyJob);
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', {});
    server.use(checks.handler, save.handler, commit.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /create project/i }));
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(save.calls).toHaveLength(1);
    expect(save.calls[0].body).toEqual({ result_json: plan });
    expect(save.calls[0].url).toMatch(/\/api\/projects\/ingest\/job-3\/$/);
    expect(checks.calls).toHaveLength(3);
    expect(commit.calls).toHaveLength(0);
    expect(readIngestDraft(99)).toBeNull();
  });

  it.each([
    ['removed project', { ...readyJob, status: 'committed', project: null }],
    ['discarded import', { ...readyJob, status: 'discarded' }],
  ])('reloads a conflicting creation before offering a fresh start for a %s', async (_label, terminalJob) => {
    keepDraft();
    let terminal = false;
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', () => {
      terminal = true;
      return HttpResponse.json({ error: 'Import no longer available' }, { status: 409 });
    });
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', () => terminal ? terminalJob : readyJob);
    server.use(checks.handler, commit.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /create project/i }));
    const forget = await screen.findByRole('button', { name: /forget this import/i });
    expect(checks.calls).toHaveLength(3);
    expect(commit.calls).toHaveLength(1);
    expect(readIngestDraft(99).pendingCommit).toBe(true);
    await user.click(forget);
    expect(screen.getByRole('button', { name: /parse source/i })).toBeInTheDocument();
    expect(readIngestDraft(99)).toBeNull();
  });

  it('recovers a creation whose response was interrupted without posting a second commit', async () => {
    keepDraft();
    let committed = false;
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', () => {
      committed = true;
      return HttpResponse.json({ error: 'Response interrupted' }, { status: 503 });
    });
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', () => committed
      ? { ...readyJob, status: 'committed', project: 44 } : readyJob);
    server.use(checks.handler, commit.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /create project/i }));
    expect(await screen.findByRole('button', { name: /check creation/i })).toBeInTheDocument();
    expect(readIngestDraft(99).pendingCommit).toBe(true);
    await user.click(screen.getByRole('button', { name: /check creation/i }));
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(commit.calls).toHaveLength(1);
    expect(checks.calls).toHaveLength(3);
    expect(readIngestDraft(99)).toBeNull();
  });

  it('safely retries a ready import with its original creation payload after refresh', async () => {
    keepDraft({ pendingCommit: true, overrides: { ...DEFAULT_OVERRIDES, bonus_amount: '12' } });
    const save = spyHandler('patch', '*/api/projects/ingest/job-3/', {});
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', { id: 44 });
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)), save.handler, commit.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /check creation/i }));
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(save.calls).toHaveLength(0);
    expect(commit.calls).toHaveLength(1);
    expect(commit.calls[0].body).toEqual({ ...plan, category_id: null, difficulty: 2, bonus_amount: '12', materials_budget: '0', due_date: null });
  });

  it('discards the existing job and clears its device draft only after confirmation', async () => {
    keepDraft();
    const discard = spyHandler('delete', '*/api/projects/ingest/job-3/', new HttpResponse(null, { status: 204 }));
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)), discard.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /^discard$/i }));
    expect(await screen.findByText('Projects list')).toBeInTheDocument();
    expect(discard.calls).toHaveLength(1);
    expect(discard.calls[0].url).toMatch(/\/api\/projects\/ingest\/job-3\/$/);
    expect(discard.calls[0].body).toBeNull();
    expect(readIngestDraft(99)).toBeNull();
  });

  it('does not restore another parent’s unfinished import', async () => {
    keepDraft({}, 98);
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', readyJob);
    server.use(checks.handler);
    renderPage();
    expect(await screen.findByRole('button', { name: /parse source/i })).toBeInTheDocument();
    expect(checks.calls).toHaveLength(0);
    expect(localStorage.getItem(ingestDraftKey(98))).not.toBeNull();
  });

  it.each([
    ['a removed job', HttpResponse.json({ detail: 'Not found.' }, { status: 404 })],
    ['a removed project', { ...readyJob, status: 'committed', project: null }],
    ['a discarded job', { ...readyJob, status: 'discarded' }],
  ])('offers a fresh start for %s without trying to delete or recreate it', async (_label, response) => {
    keepDraft({ pendingCommit: true });
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', response);
    const discard = spyHandler('delete', '*/api/projects/ingest/job-3/', {});
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', {});
    server.use(checks.handler, discard.handler, commit.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /forget this import/i }));
    expect(screen.getByRole('button', { name: /parse source/i })).toBeInTheDocument();
    expect(readIngestDraft(99)).toBeNull();
    expect(discard.calls).toHaveLength(0);
    expect(commit.calls).toHaveLength(0);
  });

  it('lets a restored failed import start again even if its creation was previously uncertain', async () => {
    keepDraft({ pendingCommit: true });
    const discard = spyHandler('delete', '*/api/projects/ingest/job-3/', new HttpResponse(null, { status: 204 }));
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json({ ...readyJob, status: 'failed', error: 'Source unavailable' })), discard.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /discard & start again/i }));
    expect(await screen.findByRole('button', { name: /parse source/i })).toBeInTheDocument();
    expect(discard.calls).toHaveLength(1);
    expect(discard.calls[0].url).toMatch(/\/api\/projects\/ingest\/job-3\/$/);
    expect(readIngestDraft(99)).toBeNull();
  });

  it('offers a safe fresh start when a job is removed after its preview opened', async () => {
    keepDraft();
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', () => checks.calls.length === 1
      ? readyJob : HttpResponse.json({ detail: 'Not found.' }, { status: 404 }));
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', {});
    server.use(checks.handler, commit.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /create project/i }));
    await user.click(await screen.findByRole('button', { name: /forget this import/i }));
    expect(screen.getByRole('button', { name: /parse source/i })).toBeInTheDocument();
    expect(readIngestDraft(99)).toBeNull();
    expect(commit.calls).toHaveLength(0);
  });

  it('keeps a later edit behind a slow autosave so older server writes cannot overwrite it', async () => {
    keepDraft();
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const writes = vi.fn();
    server.use(
      http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)),
      http.patch('*/api/projects/ingest/job-3/', async ({ request }) => {
        const body = await request.json();
        writes(body);
        if (writes.mock.calls.length === 1) await gate;
        return HttpResponse.json({});
      }),
    );
    const { user } = renderPage();
    const title = await screen.findByRole('textbox', { name: /^title$/i });
    await user.clear(title);
    await user.type(title, 'First draft');
    await waitFor(() => expect(writes).toHaveBeenCalledTimes(1));
    await user.clear(title);
    await user.type(title, 'Final draft');
    // The second debounce has elapsed when this delay finishes; its PATCH
    // must still wait for the first server write to finish.
    await new Promise(resolve => setTimeout(resolve, 750));
    expect(writes).toHaveBeenCalledTimes(1);
    release();
    await waitFor(() => expect(writes).toHaveBeenCalledTimes(2));
    expect(writes.mock.calls.map(([body]) => body.result_json.title)).toEqual(['First draft', 'Final draft']);
    expect(await screen.findByText(/edited plan is saved with this import/i)).toBeInTheDocument();
  });

  it('keeps the device draft when discarding fails', async () => {
    keepDraft();
    const discard = spyHandler('delete', '*/api/projects/ingest/job-3/', HttpResponse.json({ error: 'Try later' }, { status: 503 }));
    server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)), discard.handler);
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /^discard$/i }));
    expect(await screen.findByText('Try later')).toBeInTheDocument();
    expect(readIngestDraft(99).draft).toEqual(plan);
    expect(screen.getByRole('button', { name: /create project/i })).toBeEnabled();
    expect(discard.calls).toHaveLength(1);
  });

  it('opens an already-created project if another tab commits before discard', async () => {
    keepDraft();
    let committed = false;
    const discard = spyHandler('delete', '*/api/projects/ingest/job-3/', () => {
      committed = true;
      return HttpResponse.json({ error: 'Already committed' }, { status: 409 });
    });
    server.use(
      http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(committed
        ? { ...readyJob, status: 'committed', project: 44 } : readyJob)),
      discard.handler,
    );
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /^discard$/i }));
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(discard.calls).toHaveLength(1);
    expect(readIngestDraft(99)).toBeNull();
  });

  it.each([false, true])('handles navigation during source upload while respecting a changed session (%s)', async (changedSession) => {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const starts = vi.fn();
    server.use(http.post('*/api/projects/ingest/', async ({ request }) => {
      starts({ url: request.url, body: await request.json() });
      await gate;
      return HttpResponse.json({ id: 'job-3', status: 'pending' }, { status: 201 });
    }));
    const { user } = renderPage();
    await user.type(await screen.findByRole('textbox', { name: /tutorial url/i }), 'https://example.com/tutorial');
    await user.click(screen.getByRole('button', { name: /parse source/i }));
    await waitFor(() => expect(starts).toHaveBeenCalledOnce());
    await user.click(screen.getByRole('link', { name: /back to projects/i }));
    expect(screen.getByText('Projects list')).toBeInTheDocument();
    if (changedSession) localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'different-session');
    const responseFinished = new Promise(resolve => {
      const onResponse = ({ request }) => {
        if (new URL(request.url).pathname === '/api/projects/ingest/') {
          server.events.removeListener('response:mocked', onResponse);
          resolve();
        }
      };
      server.events.on('response:mocked', onResponse);
    });
    await act(async () => { release(); await responseFinished; });
    if (changedSession) expect(readIngestDraft(99)).toBeNull();
    else await waitFor(() => expect(readIngestDraft(99)?.jobId).toBe('job-3'));
    expect(starts.mock.calls[0][0]).toEqual({
      url: expect.stringMatching(/\/api\/projects\/ingest\/$/),
      body: { source_type: 'url', source_url: 'https://example.com/tutorial' },
    });
  });

  it('freezes edits while the original plan is being saved for creation', async () => {
    keepDraft();
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    let staged;
    const saveStarted = vi.fn();
    const commit = spyHandler('post', '*/api/projects/ingest/job-3/commit/', { id: 44 });
    server.use(
      http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)),
      http.patch('*/api/projects/ingest/job-3/', async ({ request }) => {
        staged = await request.json();
        saveStarted();
        await gate;
        return HttpResponse.json({});
      }),
      commit.handler,
    );
    const { user } = renderPage();
    await user.click(await screen.findByRole('button', { name: /create project/i }));
    await waitFor(() => expect(saveStarted).toHaveBeenCalledOnce());
    const title = screen.getByRole('textbox', { name: /^title$/i });
    expect(title).toBeDisabled();
    expect(screen.getByRole('button', { name: /^discard$/i })).toBeDisabled();
    await user.type(title, 'This must not be lost');
    release();
    expect(await screen.findByText('Created project')).toBeInTheDocument();
    expect(staged).toEqual({ result_json: plan });
    expect(commit.calls[0].body.title).toBe(plan.title);
  });

  it('checks the same job after polling exceeds the wait window', async () => {
    keepDraft({ draft: null });
    const realNow = Date.now();
    const clock = vi.spyOn(Date, 'now').mockReturnValue(realNow);
    const checks = spyHandler('get', '*/api/projects/ingest/job-3/', { ...readyJob, status: 'running' });
    const start = spyHandler('post', '*/api/projects/ingest/', {});
    server.use(checks.handler, start.handler);
    try {
      const { user } = renderPage();
      await waitFor(() => expect(checks.calls).toHaveLength(1));
      clock.mockReturnValue(realNow + 61000);
      const check = await screen.findByRole('button', { name: /check import/i }, { timeout: 2500 });
      server.use(http.get('*/api/projects/ingest/job-3/', () => HttpResponse.json(readyJob)));
      await user.click(check);
      expect(await screen.findByDisplayValue(plan.title)).toBeInTheDocument();
      expect(start.calls).toHaveLength(0);
      expect(readIngestDraft(99).jobId).toBe('job-3');
    } finally {
      clock.mockRestore();
    }
  });
});
