import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddResourceModal from './AddResourceModal.jsx';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';

vi.mock('../../../components/GoogleDrivePickerButton', () => ({
  default: ({ onPick, onOpenChange }) => (
    <button type="button" onClick={async () => {
      onOpenChange?.(true);
      try { await onPick({ file_id: 'school-pdf-1', access_token: 'synthetic-drive-token' }); }
      finally { onOpenChange?.(false); }
    }}>Choose from Google Drive</button>
  ),
}));

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddResourceModal', () => {
  it('submits a new resource', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.post(/\/api\/projects\/5\/resources\/$/, () => HttpResponse.json({ id: 1 })),
    );
    render(
      <AddResourceModal projectId={5} steps={[{ id: 10, title: 'Cut' }]} onClose={vi.fn()} onSaved={onSaved} />,
    );
    await user.type(document.querySelector('input[type="url"]'), 'https://example.com');
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('verifies a Drive PDF and saves its link under the chosen project step', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', {
      id: 'school-pdf-1', title: 'Science worksheet.pdf',
      url: 'https://drive.google.com/file/d/school-pdf-1/view',
      mime_type: 'application/pdf', resource_type: 'doc',
    });
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 11 });
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[{ id: 10, title: 'Experiment' }]} onClose={vi.fn()} onSaved={onSaved} />);
    await user.selectOptions(screen.getByLabelText('Attach to Step'), '10');
    await user.click(screen.getByRole('button', { name: /choose from google drive/i }));
    await waitFor(() => expect(screen.getByLabelText('Title (optional)')).toHaveValue('Science worksheet.pdf'));
    expect(resolve.calls).toHaveLength(1);
    expect(resolve.calls[0].body).toEqual({ file_id: 'school-pdf-1', access_token: 'synthetic-drive-token' });
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({
      project: 5, title: 'Science worksheet.pdf',
      url: 'https://drive.google.com/file/d/school-pdf-1/view', resource_type: 'doc', step: '10',
    });
    expect(onSaved).toHaveBeenCalledOnce();
    expect(document.body.textContent).not.toContain('synthetic-drive-token');
  });
});
