export const PEDESTAL_SUPPORT_ANCHOR = Object.freeze([0, 2.028465509414673, 0]);
export const EGG_CLEARANCE_METERS = 0.002;
export const PEDESTAL_EGG_ASSETS = Object.freeze([
  'normal-egg', 'legendary-egg', 'legendary-egg-idle-breath',
  'legendary-egg-idle-wobble', 'legendary-egg-hatching-soon',
]);

export function pedestalPlaybackIdentity(staged, eggAssetId) {
  return JSON.stringify([
    staged?.manifestUrl, staged?.manifestSha256, eggAssetId,
    (staged?.release?.files || []).map((file) => [file.path, staged.resolveUrl(file.path)]),
  ]);
}
