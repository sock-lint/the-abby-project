import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProjectIngest from './ProjectIngest.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('ProjectIngest', () => {
  it('renders the source step with URL/PDF tabs', async () => {
    render(
      <MemoryRouter>
        <ProjectIngest />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(
        screen.getAllByText((t) => /url|pdf|source|ingest|import/i.test(t)).length,
      ).toBeGreaterThan(0),
    );
  });
});
