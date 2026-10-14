import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import OnboardingChecklist from './OnboardingChecklist';

function renderChecklist(data) {
  return render(<MemoryRouter><OnboardingChecklist data={data} /></MemoryRouter>);
}

describe('OnboardingChecklist', () => {
  it('uses the flat child count without inventing incomplete chore and reward steps', () => {
    renderChecklist({ children_count: 2, active_projects: [] });
    expect(screen.queryByRole('button', { name: /add a child/i })).toBeNull();
    expect(screen.queryByText(/of \d+ complete/i)).toBeNull();
    expect(screen.getByRole('heading', { name: 'Getting started' })).toBeInTheDocument();
    expect(screen.getByText(/optional ways to set up your family's activities/i)).toBeInTheDocument();
  });

  it('only prompts for a child when the server confirms none exist', () => {
    renderChecklist({ children_count: 0 });
    expect(screen.getByRole('button', { name: /add a child to your family/i })).toBeInTheDocument();
  });

  it('does not prompt for an unverified child count', () => {
    renderChecklist({});
    expect(screen.queryByRole('button', { name: /add a child/i })).toBeNull();
  });

  it('keeps optional guidance dismissible across visits', async () => {
    const user = userEvent.setup();
    const view = renderChecklist({ children_count: 1 });
    await user.click(screen.getByRole('button', { name: /dismiss checklist/i }));
    expect(screen.queryByText('Getting started')).toBeNull();
    view.unmount();
    renderChecklist({ children_count: 1 });
    expect(screen.queryByText('Getting started')).toBeNull();
  });
});

it('keeps optional guidance dismissal scoped to the parent and family', async () => {
  const user = userEvent.setup();
  const first = { id: 99, family: { id: 1 } };
  const view = render(<MemoryRouter><OnboardingChecklist data={{ children_count: 1 }} user={first} /></MemoryRouter>);
  await user.click(screen.getByRole('button', { name: /dismiss checklist/i }));
  view.rerender(<MemoryRouter><OnboardingChecklist data={{ children_count: 1 }} user={{ id: 100, family: { id: 2 } }} /></MemoryRouter>);
  expect(screen.getByRole('heading', { name: 'Getting started' })).toBeInTheDocument();
  view.rerender(<MemoryRouter><OnboardingChecklist data={{ children_count: 1 }} user={first} /></MemoryRouter>);
  expect(screen.queryByText('Getting started')).toBeNull();
});
