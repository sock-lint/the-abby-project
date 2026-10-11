// Older workers cached token-authenticated JSON by URL alone. Keep static,
// font and media caches, but remove every legacy private-response cache.
export async function purgePrivateApiCaches() {
  try {
    if (!globalThis.caches) return;
    const names = await caches.keys();
    await Promise.all(names.filter((name) => /^api-reads(?:$|-)/.test(name))
      .map((name) => caches.delete(name)));
  } catch {
    // Cache Storage is unavailable in some private browsing modes.
  }
}
