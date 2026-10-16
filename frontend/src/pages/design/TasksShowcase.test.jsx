import { describe, expect, it, vi } from 'vitest';
import { render, renderWithProviders, screen, userEvent, waitFor, within } from '../../test/render';
import DesignShowcase from '../__design';
import TasksShowcase from './TasksShowcase';

function runningGoal() {
  return screen.getByRole('article', { name: 'Run 2 miles this week' });
}

describe('Task folio design showcase', () => {
  it('uses the shared Tasks shell with parent focus, three bonus goals and collapsed browsing/history', async () => {
    const { user } = renderWithProviders(<TasksShowcase />, { withAuth: false });
    const folio = screen.getByRole('region', { name: 'Challenges overview' });
    expect(folio.querySelector('[data-folio-verso="true"]')).toBeInTheDocument();
    expect(folio.querySelector('[data-folio-recto="true"]')).toBeInTheDocument();
    expect(runningGoal()).toBeInTheDocument();
    expect(within(runningGoal()).getByText('From your parent')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Practice piano for 60 minutes' })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Read together next week' })).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Bonus progress' })).getAllByRole('article')).toHaveLength(3);
    for (const name of ['Keep moving', 'Homework rhythm', 'Creative practice']) {
      expect(screen.getByRole('article', { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole('article', { name: 'Focus time' })).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'Build momentum' })).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'A week of practice' })).not.toBeInTheDocument();
    const browse = screen.getByText('Browse bonus challenges', { selector: 'summary' });
    const history = screen.getByText(/^History/, { selector: 'summary' });
    expect(browse.closest('details')).not.toHaveAttribute('open');
    expect(history.closest('details')).not.toHaveAttribute('open');
    await user.click(browse);
    expect(await screen.findByRole('article', { name: 'Focus time' })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Build momentum' })).toBeInTheDocument();
    await user.click(history);
    expect(await screen.findByRole('article', { name: 'A week of practice' })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Earlier challenge' })).toBeInTheDocument();
  });

  it('opens actual goal details and changes a pin locally without changing earned progress or making requests', async () => {
    localStorage.clear();
    const request = vi.spyOn(globalThis, 'fetch');
    try {
      const { user } = renderWithProviders(<TasksShowcase />, { withAuth: false });
      const opener = within(runningGoal()).getByRole('button', { name: 'View Run 2 miles this week' });
      await user.click(opener);
      const detail = screen.getByRole('dialog', { name: 'Run 2 miles this week' });
      expect(within(detail).getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
      expect(within(detail).getByText('Logged Running distance. Every valid running session this week counts.')).toBeInTheDocument();
      expect(within(detail).getByRole('progressbar', { name: 'Run 2 miles this week progress' })).toHaveAttribute('aria-valuenow', '1.25');
      await user.click(within(detail).getByRole('button', { name: 'Unpin' }));
      expect(within(detail).getByRole('button', { name: 'Pin to Today' })).toHaveAttribute('aria-pressed', 'false');
      expect(within(detail).getByRole('progressbar', { name: 'Run 2 miles this week progress' })).toHaveAttribute('aria-valuenow', '1.25');
      await user.keyboard('{Escape}');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(runningGoal()).toBeInTheDocument();
      await waitFor(() => expect(within(runningGoal()).getByRole('button', { name: 'View Run 2 miles this week' })).toHaveFocus());
      expect(within(runningGoal()).getByRole('progressbar', { name: 'Run 2 miles this week progress' })).toHaveAttribute('aria-valuenow', '1.25');
      expect(request).not.toHaveBeenCalled();
    } finally {
      request.mockRestore();
    }
  });

  it('previews the parent presentation while retaining saved goals and hiding child pin controls', async () => {
    const { user } = renderWithProviders(<TasksShowcase />, { withAuth: false });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Preview role' }), 'parent');
    expect(within(runningGoal()).getByText('Parent goal')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Sample daily bonus' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Unpin|Pin to Today)$/ })).not.toBeInTheDocument();
    await user.click(within(runningGoal()).getByRole('button', { name: 'View Run 2 miles this week' }));
    const detail = screen.getByRole('dialog', { name: 'Run 2 miles this week' });
    expect(within(detail).getByRole('progressbar', { name: 'Run 2 miles this week progress' })).toHaveAttribute('aria-valuenow', '1.25');
    expect(within(detail).queryByRole('button', { name: /^(Unpin|Pin to Today)$/ })).not.toBeInTheDocument();
  });

  it('registers a discoverable design-gallery entry connected to the real Task folio preview without an account', () => {
    localStorage.clear();
    const request = vi.spyOn(globalThis, 'fetch');
    try {
      renderWithProviders(<DesignShowcase />, { withAuth: false });
      const navigation = screen.getByRole('navigation', { name: 'Showcase sections' });
      expect(within(navigation).getByRole('link', { name: 'Task folio' })).toHaveAttribute('href', '#task-folio');
      const entry = screen.getByRole('region', { name: 'Task folio' });
      expect(entry).toHaveAttribute('id', 'task-folio');
      expect(within(entry).getByRole('region', { name: 'Challenges overview' })).toBeInTheDocument();
      expect(within(entry).getByRole('combobox', { name: 'Preview role' })).toHaveValue('child');
      expect(request).not.toHaveBeenCalled();
    } finally {
      request.mockRestore();
    }
  });

  it('opens goal details from the standalone design route without an outer router or account', async () => {
    localStorage.clear();
    const request = vi.spyOn(globalThis, 'fetch');
    try {
      const user = userEvent.setup();
      render(<DesignShowcase />);
      const entry = screen.getByRole('region', { name: 'Task folio' });
      await user.click(within(entry).getByRole('button', { name: 'View Run 2 miles this week' }));
      const detail = screen.getByRole('dialog', { name: 'Run 2 miles this week' });
      expect(within(detail).getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
      await user.keyboard('{Escape}');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(request).not.toHaveBeenCalled();
    } finally {
      request.mockRestore();
    }
  });
});
