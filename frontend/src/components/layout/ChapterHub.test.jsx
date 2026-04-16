import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ChapterHub from './ChapterHub.jsx';

const tabs = [
  { id: 'a', label: 'Alpha', render: () => <div>content-a</div> },
  { id: 'b', label: 'Beta', render: () => <div>content-b</div> },
];

function renderHub({ route = '/', defaultTabId } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ChapterHub
        title="Test Hub"
        kicker="kicker"
        tabs={tabs}
        defaultTabId={defaultTabId}
      />
    </MemoryRouter>,
  );
}

describe('ChapterHub', () => {
  it('renders title, kicker, and first tab by default', () => {
    renderHub();
    expect(screen.getByRole('heading', { name: 'Test Hub' })).toBeInTheDocument();
    expect(screen.getByText('kicker')).toBeInTheDocument();
    expect(screen.getByText('content-a')).toBeInTheDocument();
  });

  it('switches to ?tab= matched tab', () => {
    renderHub({ route: '/?tab=b' });
    expect(screen.getByText('content-b')).toBeInTheDocument();
  });

  it('falls back to defaultTabId when ?tab= is unknown', () => {
    renderHub({ route: '/?tab=missing', defaultTabId: 'b' });
    expect(screen.getByText('content-b')).toBeInTheDocument();
  });

  it('falls back to first tab when no defaults match', () => {
    renderHub({ route: '/?tab=zzz' });
    expect(screen.getByText('content-a')).toBeInTheDocument();
  });

  it('clicking a tab updates the query string and content', async () => {
    const user = userEvent.setup();
    renderHub();
    await user.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(screen.getByText('content-b')).toBeInTheDocument();
  });

  it('sets aria-selected on the active tab', () => {
    renderHub({ route: '/?tab=b' });
    expect(
      screen.getByRole('tab', { name: 'Beta' }).getAttribute('aria-selected'),
    ).toBe('true');
  });
});
