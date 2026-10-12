// Growth alone never unlocks an evolved portrait. The server keeps the pet
// row after evolution, so those rows use the confirmed mount form too.
export function petSpriteKeys(pet) {
  const base = pet?.species?.sprite_key || null;
  const evolved = pet?.evolved_to_mount === true && Boolean(base);
  return {
    spriteKey: evolved ? `${base}-mount` : base,
    fallbackSpriteKey: evolved ? base : null,
  };
}
