/** Static view normalization uses only this stage's native idle bounds. Camera
 * focus follows their center; geometry, joint tracks and native clearance stay
 * at their supplied positions throughout every take of the selected stage. */
export function rosterFraming(bounds) {
  if (!bounds) return { scale: 1, center: undefined };
  const scale = 2.8 / Math.max(...bounds.max.map((value, axis) => value - bounds.min[axis]), 0.001);
  return { scale, center: bounds.min.map((value, axis) => (value + bounds.max[axis]) / 2 * scale) };
}
