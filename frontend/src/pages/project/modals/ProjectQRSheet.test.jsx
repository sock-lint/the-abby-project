import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import ProjectQRSheet from './ProjectQRSheet.jsx';
import { server } from '../../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('ProjectQRSheet', () => {
  it('renders the QR image on success', async () => {
    server.use(
      http.get(/\/api\/projects\/5\/qr\/$/, () => new HttpResponse('qr-bytes')),
    );
    window.URL.createObjectURL = vi.fn(() => 'blob:qr');
    render(<ProjectQRSheet projectId={5} projectTitle="Alpha" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByAltText(/qr code for alpha/i)).toBeInTheDocument());
  });

  it('shows failure state when QR fetch errors', async () => {
    server.use(
      http.get(/\/api\/projects\/5\/qr\/$/, () => new HttpResponse(null, { status: 500 })),
    );
    render(<ProjectQRSheet projectId={5} projectTitle="X" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/failed to load/i)).toBeInTheDocument());
  });
});
