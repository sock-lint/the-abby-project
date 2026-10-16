import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, fireEvent, renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import { buildParent } from '../test/factories';
import { PwaStatusProvider } from './PwaStatusProvider';
import { usePwaStatus } from './pwaStatus.context';
import QuickActionsSheet from '../components/layout/QuickActionsSheet';
import HoardsTab from '../pages/treasury/HoardsTab';
import CoinExchangeModal from '../pages/rewards/CoinExchangeModal';
import RequestChangesModal from '../pages/project/modals/RequestChangesModal';
import PrinterConfigPanel from '../pages/forge/PrinterConfigPanel';
import ApprovalSheet from '../pages/forge/ApprovalSheet';
import SpriteGenerateModal from '../pages/manage/SpriteGenerateModal';

const registration = vi.hoisted(() => ({ callbacks: null, update: vi.fn() }));
vi.mock('./registerPromptWorker', () => ({ registerPromptWorker: (callbacks) => {
  registration.callbacks = callbacks;
  return { update: registration.update, dispose: () => {} };
} }));

function Apply() {
  const { applyUpdate, updateBlocked } = usePwaStatus();
  return <button onClick={applyUpdate}>Apply update {updateBlocked ? 'blocked' : 'available'}</button>;
}

const REQUEST = { id: 7, title: 'Synthetic print', estimated_grams: null, estimated_minutes: null };
const cases = [
  {
    name: 'quick clock notes', element: (onClose) => <QuickActionsSheet status={{ project_title: 'Synthetic project' }} isClocked elapsedSecs={60} onClose={onClose} onClockReload={async () => {}} />,
    open: /Stop clock/, field: () => screen.getByRole('textbox'), draft: 'Keep this activity note', submit: 'Clock out', endpoint: '*/api/clock/',
  },
  {
    name: 'savings goal', element: () => <HoardsTab />, open: /New savings goal/i,
    field: () => screen.getByLabelText(/What are you saving for/i), draft: 'Synthetic goal', submit: 'Start saving', endpoint: '*/api/savings-goals/',
    complete: () => fireEvent.change(screen.getByLabelText(/Target amount/i), { target: { value: '10' } }),
  },
  {
    name: 'coin exchange', element: (onClose) => <CoinExchangeModal exchangeRate={10} onClose={onClose} onSaved={() => {}} />,
    field: () => screen.getByRole('spinbutton'), draft: '5', submit: 'Request exchange', endpoint: '*/api/coins/exchange/',
  },
  {
    name: 'project feedback', element: (onClose, onSubmit) => <RequestChangesModal onClose={onClose} onSubmit={onSubmit} />,
    field: () => screen.getByLabelText('What should they change?'), draft: 'Keep this project feedback', submit: 'Send',
  },
  {
    name: 'printer configuration', element: () => <PrinterConfigPanel printers={[]} />, open: /Add printer/i,
    field: () => screen.getByLabelText('Name'), draft: 'Synthetic printer', submit: 'Add printer', endpoint: '*/api/printers/',
    complete: () => {
      fireEvent.change(screen.getByLabelText('Serial'), { target: { value: 'SYNTHETIC-SERIAL' } });
      fireEvent.change(screen.getByLabelText('Host'), { target: { value: '192.0.2.1' } });
      fireEvent.change(screen.getByLabelText('Access code'), { target: { value: 'synthetic-code' } });
    },
  },
  {
    name: 'print approval', element: (onClose) => <ApprovalSheet request={REQUEST} onClose={onClose} />,
    field: () => screen.getByLabelText('Note (optional)'), draft: 'Keep this decision note', submit: 'Approve', endpoint: '*/api/print-requests/7/approve/',
  },
  {
    name: 'sprite request', element: (onClose) => <SpriteGenerateModal onClose={onClose} />,
    field: () => screen.getByLabelText('Prompt'), draft: 'Keep this synthetic sprite prompt', submit: 'Create sprite', endpoint: '*/api/sprites/admin/generate/',
    complete: () => fireEvent.change(screen.getByLabelText('Slug'), { target: { value: 'synthetic-sprite' } }),
  },
];

beforeEach(() => {
  registration.callbacks = null;
  registration.update.mockReset();
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/savings-goals/', () => HttpResponse.json([])),
    http.get('*/api/projects/', () => HttpResponse.json([])),
    http.get('*/api/balance/', () => HttpResponse.json({ balance: 50 })),
  );
});

async function openForm(example, onClose, onSubmit) {
  renderWithProviders(<PwaStatusProvider><Apply />{example.element(onClose, onSubmit)}</PwaStatusProvider>);
  if (example.open) fireEvent.click(await screen.findByRole('button', { name: example.open }));
  await waitFor(() => expect(example.field()).toBeInTheDocument());
  await waitFor(() => expect(registration.callbacks).not.toBeNull());
  act(() => registration.callbacks.onNeedRefresh());
  return example.field();
}

describe('manual sheet work protects updates and passive dismissal', () => {
  it.each(cases)('preserves unfinished $name', async (example) => {
    const onClose = vi.fn();
    const onSubmit = vi.fn();
    const field = await openForm(example, onClose, onSubmit);
    expect(screen.getByRole('button', { name: 'Apply update available' })).toBeInTheDocument();
    fireEvent.change(field, { target: { value: example.draft } });
    if (!['quick clock notes', 'print approval'].includes(example.name)) {
      expect(screen.getByRole('button', { name: /^Discard (draft|changes)$/ })).toBeInTheDocument();
    }
    fireEvent.click(await screen.findByRole('button', { name: 'Apply update blocked' }));
    expect(registration.update).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    const confirmation = await screen.findByRole('alertdialog', { name: 'Discard changes?' });
    expect(onClose).not.toHaveBeenCalled();
    expect(field).toHaveValue(example.draft === '5' ? 5 : example.draft);
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Cancel' }));
    expect(field).toHaveValue(example.draft === '5' ? 5 : example.draft);
    fireEvent.change(field, { target: { value: '' } });
    await screen.findByRole('button', { name: 'Apply update available' });
  });

  it('requires an explicit discard to leave unfinished clock notes with the pane Back action', async () => {
    const field = await openForm(cases[0], vi.fn());
    fireEvent.change(field, { target: { value: 'Keep this activity note' } });
    fireEvent.click(screen.getByRole('button', { name: /Back/ }));
    const confirmation = await screen.findByRole('alertdialog', { name: 'Discard clock-out notes?' });
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Cancel' }));
    expect(field).toHaveValue('Keep this activity note');
    fireEvent.click(screen.getByRole('button', { name: /Back/ }));
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Discard' }));
    await screen.findByRole('dialog', { name: 'Quick actions' });
    await screen.findByRole('button', { name: 'Apply update available' });
  });

  it('keeps edited notes while leaving the reject confirmation and releases the guard after approval', async () => {
    server.use(http.post('*/api/print-requests/7/approve/', () => HttpResponse.json({ ...REQUEST, plate_filename: 'synthetic-print.3mf' })));
    const field = await openForm(cases[5], vi.fn());
    fireEvent.change(field, { target: { value: 'Keep this decision note' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    fireEvent.keyDown(await screen.findByRole('dialog', { name: /Reject/ }), { key: 'Escape' });
    expect(await screen.findByLabelText('Note (optional)')).toHaveValue('Keep this decision note');
    expect(screen.getByRole('button', { name: 'Apply update blocked' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await screen.findByRole('dialog', { name: 'Approved' });
    await screen.findByRole('button', { name: 'Apply update available' });
  });

  it('releases the sprite-request guard on the confirmed success screen', async () => {
    server.use(http.post('*/api/sprites/admin/generate/', () => HttpResponse.json({ slug: 'synthetic-sprite', frame_count: 1, frame_width_px: 64, frame_height_px: 64 })));
    const field = await openForm(cases[6], vi.fn());
    fireEvent.change(field, { target: { value: 'Keep this synthetic sprite prompt' } });
    cases[6].complete();
    fireEvent.click(screen.getByRole('button', { name: 'Create sprite' }));
    await screen.findByRole('dialog', { name: 'Sprite created' });
    await screen.findByRole('button', { name: 'Apply update available' });
  });

  it.each(cases)('blocks dismissal during a pending $name write and retains edited input', async (example) => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const onClose = vi.fn();
    const onSubmit = vi.fn(() => pending);
    if (example.endpoint) server.use(http.post(example.endpoint, async () => {
      await pending;
      return HttpResponse.json({ detail: 'Synthetic save failure' }, { status: 500 });
    }));
    const field = await openForm(example, onClose, onSubmit);
    fireEvent.change(field, { target: { value: example.draft } });
    example.complete?.();
    const submit = within(screen.getByRole('dialog')).getByRole('button', { name: example.submit, exact: true });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Apply update blocked' }));
    expect(registration.update).not.toHaveBeenCalled();
    await act(async () => release());
    await waitFor(() => expect(submit).toBeEnabled());
    expect(field).toHaveValue(example.draft === '5' ? 5 : example.draft);
  });
});
