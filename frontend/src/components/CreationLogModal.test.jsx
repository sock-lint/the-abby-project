import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import CreationLogModal from './CreationLogModal';

// URL.createObjectURL isn't in jsdom; downscaleImage skips the canvas
// round-trip on tiny files, but we mock it so the test never relies on
// browser image decoding.
vi.mock('../utils/image', () => ({
  downscaleImage: async (file) => file,
}));

function stubSkills() {
  server.use(
    http.get('*/api/skills/', () =>
      HttpResponse.json([
        { id: 11, name: 'Drawing', category_name: 'Art & Crafts' },
        { id: 12, name: 'Painting', category_name: 'Art & Crafts' },
        { id: 21, name: 'Baking', category_name: 'Cooking' },
        { id: 99, name: 'Algebra', category_name: 'Math' }, // should be filtered out
      ]),
    ),
  );
}

describe('CreationLogModal', () => {
  it('renders only creative-subset skills in the primary picker', async () => {
    stubSkills();
    renderWithProviders(<CreationLogModal onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /primary skill/i })).toBeInTheDocument();
    });

    const primary = screen.getByRole('combobox', { name: /primary skill/i });
    const options = within(primary).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(expect.arrayContaining(['Drawing', 'Painting', 'Baking']));
    expect(options).not.toContain('Algebra');
  });

  it('submits multipart POST when the form is filled out', async () => {
    stubSkills();

    // FormData spy — spyHandler only parses JSON; we need a custom handler
    // that captures multipart fields via the raw Web Request formData().
    const calls = [];
    server.use(
      http.post(/\/api\/creations\/$/, async ({ request }) => {
        try {
          const fd = await request.formData();
          const entries = {};
          for (const [k, v] of fd.entries()) {
            // Normalise File/Blob to a plain object — jsdom's `File`
            // isn't always the same class as MSW's, so `instanceof File`
            // is unreliable. Duck-type on `.size` + `.type`.
            if (v && typeof v === 'object' && 'size' in v) {
              entries[k] = { __file: v.name || 'blob', size: v.size, type: v.type };
            } else {
              entries[k] = v;
            }
          }
          calls.push({ url: request.url, entries });
          return HttpResponse.json({ id: 42 }, { status: 201 });
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error('handler threw', err);
          calls.push({ url: request.url, entries: null, error: String(err) });
          return HttpResponse.json({ id: 42 }, { status: 201 });
        }
      }),
    );

    const onSaved = vi.fn();
    const onClose = vi.fn();
    const { user } = renderWithProviders(
      <CreationLogModal onClose={onClose} onSaved={onSaved} />,
    );

    // Wait until the skills API has landed — select becomes non-disabled
    // once useApi's loading flag flips.
    await waitFor(() => {
      const sel = screen.getByRole('combobox', { name: /primary skill/i });
      expect(sel).not.toBeDisabled();
    });

    // Upload a tiny fake image.
    const file = new File(['x'.repeat(10)], 'art.jpg', { type: 'image/jpeg' });
    const photoInput = screen.getByLabelText(/photo/i);
    await user.upload(photoInput, file);

    // Pick primary skill.
    const primary = screen.getByRole('combobox', { name: /primary skill/i });
    await user.selectOptions(primary, '11');

    const submitBtn = screen.getByRole('button', { name: /log creation/i });
    await waitFor(() => expect(submitBtn).not.toBeDisabled());
    await user.click(submitBtn);

    await waitFor(() => expect(calls).toHaveLength(1), { timeout: 2000 });
    expect(calls[0].url).toMatch(/\/api\/creations\/$/);
    expect(calls[0].entries.primary_skill_id).toBe('11');
    // Image field is present as a File/Blob (downscaleImage may have re-blobbed it).
    expect(calls[0].entries.image).toMatchObject({ __file: expect.any(String) });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('shows the moss "first 2 per day earn XP" hint when remaining_with_xp > 0', async () => {
    stubSkills();
    server.use(
      http.get('*/api/creations/today_status/', () =>
        HttpResponse.json({ count: 1, limit: 2, remaining_with_xp: 1 }),
      ),
    );
    renderWithProviders(<CreationLogModal onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(
        screen.getByText(/this would be 2 of 2/i),
      ).toBeInTheDocument();
    });
  });

  it('shows the ember "no XP" warning when remaining_with_xp is 0', async () => {
    stubSkills();
    server.use(
      http.get('*/api/creations/today_status/', () =>
        HttpResponse.json({ count: 2, limit: 2, remaining_with_xp: 0 }),
      ),
    );
    renderWithProviders(<CreationLogModal onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(
        screen.getByText(/won.t earn xp/i),
      ).toBeInTheDocument();
    });
  });

  it('omits the cap hint until the today_status payload lands', async () => {
    stubSkills();
    // No ``today_status`` handler override — default permissive handler
    // returns an empty list, which the modal treats as "data not present".
    renderWithProviders(<CreationLogModal onClose={() => {}} onSaved={() => {}} />);
    // Status hint ``role="status"`` is the only one in this modal — assert
    // it's absent at first paint (the form itself has no other role="status").
    expect(screen.queryByText(/will earn xp|won.t earn xp/i)).toBeNull();
  });

  it('rejects audio files over 10 MB with an inline error', async () => {
    stubSkills();
    const { user } = renderWithProviders(
      <CreationLogModal onClose={() => {}} onSaved={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/audio/i)).toBeInTheDocument();
    });

    // Fake a big file via Object.defineProperty since new File() ignores .size.
    const big = new File(['x'], 'song.mp3', { type: 'audio/mpeg' });
    Object.defineProperty(big, 'size', { value: 11 * 1024 * 1024 });

    const audioInput = screen.getByLabelText(/audio/i);
    await user.upload(audioInput, big);

    expect(await screen.findByText(/too big/i)).toBeInTheDocument();
  });
});
