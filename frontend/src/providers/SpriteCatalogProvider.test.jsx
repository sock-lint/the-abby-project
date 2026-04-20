import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderHook, waitFor } from '@testing-library/react';
import { SpriteCatalogProvider, useSpriteCatalog } from './SpriteCatalogProvider';
import { server } from '../test/server';

function wrap({ children }) {
  return <SpriteCatalogProvider>{children}</SpriteCatalogProvider>;
}

const fakeCatalog = {
  etag: 'abc123def456',
  sprites: {
    dragon: { url: 'https://s.example/dragon.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' },
    flame: { url: 'https://s.example/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal' },
  },
};

describe('SpriteCatalogProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    server.use(
      http.get('/api/sprites/catalog/', () =>
        HttpResponse.json(fakeCatalog, { headers: { ETag: `"${fakeCatalog.etag}"` } })
      )
    );
  });

  it('fetches the catalog and exposes getSpriteUrl/getSpriteMeta', async () => {
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    await waitFor(() => expect(result.current.getSpriteUrl('dragon')).toBe('https://s.example/dragon.png'));
    expect(result.current.getSpriteUrl('unknown')).toBeNull();

    const meta = result.current.getSpriteMeta('flame');
    expect(meta).toEqual({
      url: 'https://s.example/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal',
    });
  });

  it('persists catalog to localStorage for warm mounts', async () => {
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    await waitFor(() => expect(result.current.getSpriteUrl('dragon')).toBeTruthy());
    expect(JSON.parse(localStorage.getItem('spriteCatalog')).sprites.dragon).toBeTruthy();
    expect(localStorage.getItem('spriteCatalogEtag')).toBe(fakeCatalog.etag);
  });

  it('honors 304 Not Modified by using cached data', async () => {
    localStorage.setItem('spriteCatalogEtag', fakeCatalog.etag);
    localStorage.setItem('spriteCatalog', JSON.stringify(fakeCatalog));

    server.use(
      http.get('/api/sprites/catalog/', () => new HttpResponse(null, { status: 304 }))
    );
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    await waitFor(() => expect(result.current.getSpriteUrl('dragon')).toBeTruthy());
  });

  it('returns null for unknown slug while catalog is still loading', () => {
    const { result } = renderHook(() => useSpriteCatalog(), { wrapper: wrap });
    // before waitFor triggers — fetch hasn't resolved
    expect(result.current.getSpriteUrl('dragon')).toBeNull();
  });
});
