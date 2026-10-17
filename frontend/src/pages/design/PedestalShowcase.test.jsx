import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '../../test/render';
import PedestalShowcase from './PedestalShowcase';
import { DesignPreviewContext } from './preview.context';
import { PEDESTAL_IMAGE_IDS, PEDESTAL_EGG_IDS } from '../../pedestal/pedestalRelease';
import { selectDropdown } from '../../test/selectDropdown';

vi.mock('../../pedestal/PedestalPreview', () => ({ default: ({ eggAssetId, animate }) => <div role="img" aria-label="Decorative model preview" data-egg={eggAssetId || 'pedestal-only'} data-animate={String(animate)} /> }));
vi.mock('../../pedestal/pedestalRelease', async () => {
  const actual = await vi.importActual('../../pedestal/pedestalRelease');
  return { ...actual, resolvePedestalImage: (assetId, variantId = 'web') => ({ url: `/private/synthetic-${assetId}-${variantId}.png`, width: variantId === 'native' ? 1024 : 512, height: variantId === 'native' ? 1024 : 512, assetId, variantId }) };
});

describe('Pedestal and card design preview', () => {
  it('selects each separate rig and pauses local motion without sending API requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const { user } = renderWithProviders(<PedestalShowcase />, { withAuth: false });
    const picker = screen.getByRole('combobox', { name: 'Egg artwork' });
    for (const assetId of [...PEDESTAL_EGG_IDS, '']) {
      await selectDropdown(user, picker, assetId);
      expect(screen.getByRole('img', { name: 'Decorative model preview' })).toHaveAttribute('data-egg', assetId || 'pedestal-only');
    }
    await user.click(screen.getByRole('checkbox', { name: 'Play native loops' }));
    expect(screen.getByRole('img', { name: 'Decorative model preview' })).toHaveAttribute('data-animate', 'false');
    expect(screen.getByText(/HatchingSoon repeats anticipation/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('loads all 19 web canvases only when requested and selects native for one image deliberately', async () => {
    const { container, user } = renderWithProviders(<PedestalShowcase />, { withAuth: false });
    expect(container.querySelector('[data-pedestal-image-gallery]')).toBeNull();
    await user.click(screen.getByRole('checkbox', { name: 'Show all 19 web images' }));
    const gallery = container.querySelector('[data-pedestal-image-gallery]');
    expect(gallery.querySelectorAll('img')).toHaveLength(19);
    for (const assetId of PEDESTAL_IMAGE_IDS) {
      const img = gallery.querySelector(`[data-pedestal-image="${assetId}"] img`);
      expect(img).toHaveAttribute('width', '512');
      expect(img).toHaveAttribute('loading', 'lazy');
    }
    await selectDropdown(user, screen.getByRole('combobox', { name: 'UI artwork' }), 'card-front-nature');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Selected image resolution' }), 'native');
    expect(container.querySelector('[data-pedestal-image="card-front-nature"][data-image-variant="native"] img')).toHaveAttribute('width', '1024');
    expect(gallery.querySelectorAll('[data-image-variant="native"]')).toHaveLength(0);
    await user.click(screen.getByRole('checkbox', { name: 'Show all 19 web images' }));
    expect(container.querySelector('[data-pedestal-image-gallery]')).toBeNull();
  });

  it('keeps long application text independent from complete card faces', () => {
    const { container } = renderWithProviders(<DesignPreviewContext.Provider value={{ longContent: true }}><PedestalShowcase /></DesignPreviewContext.Provider>, { withAuth: false });
    const opening = container.querySelector('[data-pedestal-frame-content]');
    expect(within(opening).getByRole('heading', { name: /very long example heading/ })).toBeInTheDocument();
    expect(opening.textContent).toMatch(/Long names and larger text can be read/);
    expect(opening.querySelector('img')).toBeNull();
    expect(screen.getByText(/Faces already include their emblems/)).toBeInTheDocument();
  });
});
