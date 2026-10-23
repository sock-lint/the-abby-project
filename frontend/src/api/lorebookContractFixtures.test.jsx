import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import childGuide from '../../../contracts/api/fixtures/lorebook-child-baby-chick.json';
import parentGuide from '../../../contracts/api/fixtures/lorebook-parent-reference.json';
import Lorebook from '../pages/Lorebook.jsx';
import GuideSection from '../pages/manage/GuideSection.jsx';
import { renderWithProviders } from '../test/render.jsx';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';

// Django withholds Chick's unreached form names from a child's Guide; React
// renders the server's copy as-is on both the Guide and Manage surfaces.
async function petsEntry(account, body, ui, route) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/lorebook/', () => HttpResponse.json(body)),
  );
  const { user } = renderWithProviders(ui, { route });
  await user.click(await screen.findByRole('tab', { name: /^Challenges & Pets,/ }));
  await user.click(await screen.findByRole('button', { name: /^Pets ·/ }));
  return screen.findByRole('dialog', { name: 'Pets' });
}

describe('Guide surprise response fixtures', () => {
  it('shows a baby-Chick child generic later forms', async () => {
    const dialog = await petsEntry(buildUser({ id: 17 }), childGuide, <Lorebook />, '/atlas?tab=lorebook');
    expect(dialog).toHaveTextContent('For Chick, these forms are Chick, its middle form and its grown form.');
    expect(dialog.textContent).not.toMatch(/\b(Fledgling|Bird)\b/);
  });

  it('keeps the same child copy on the Manage Guide route', async () => {
    const dialog = await petsEntry(buildUser({ id: 17 }), childGuide, <GuideSection />, '/manage?tab=Guide');
    expect(dialog.textContent).not.toMatch(/\b(Fledgling|Bird)\b/);
  });

  it('shows parents the full reference', async () => {
    const dialog = await petsEntry(buildParent({ id: 16 }), parentGuide, <GuideSection />, '/manage?tab=Guide');
    expect(dialog).toHaveTextContent('For Chick, these forms are Chick, Fledgling and Bird.');
  });
});
