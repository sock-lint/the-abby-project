const DURATIONS = { hop: 0.75, twirl: 1.2, bow: 0.9 };

/** Local movement of the complete approved model, never its supplied bones. */
export function createAvatarReactions(root) {
  const position = root.position.clone();
  const rotation = root.rotation.clone();
  let action = null;
  let elapsed = 0;

  const reset = () => {
    root.position.copy(position);
    root.rotation.copy(rotation);
    action = null;
    elapsed = 0;
  };

  return {
    get playing() { return action !== null; },
    play(next) {
      if (!Object.hasOwn(DURATIONS, next)) return false;
      reset();
      action = next;
      return true;
    },
    update(delta) {
      if (!action || !Number.isFinite(delta)) return;
      // A backgrounded frame must not jump through or extend the pose.
      elapsed += Math.max(0, Math.min(delta, 0.05));
      const progress = Math.min(1, elapsed / DURATIONS[action]);
      root.position.copy(position);
      root.rotation.copy(rotation);
      if (action === 'hop') root.position.y += 0.22 * Math.sin(Math.PI * progress);
      if (action === 'twirl') root.rotation.y += Math.PI * (1 - Math.cos(Math.PI * progress));
      if (action === 'bow') root.rotation.x += 0.22 * Math.sin(Math.PI * progress);
      if (progress === 1) reset();
    },
    reset,
  };
}
