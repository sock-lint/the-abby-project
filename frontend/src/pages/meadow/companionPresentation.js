// Licensed art is staged privately for release builds. A public checkout can
// still render the authored placeholder without importing a missing module.
export function resolveCompanionPresentation(presentation, art, licensedPresentation, licensedArt) {
  const fallback = presentation.companion;
  const configured = licensedPresentation?.companion;
  const portrait = configured && licensedArt?.(configured.portrait);
  const useLicensed = licensedPresentation?.schema_version === presentation.schema_version
    && configured?.id === fallback.id
    && typeof configured.label === 'string' && configured.label.trim() !== ''
    && Boolean(portrait);
  const companion = useLicensed ? configured : fallback;
  const resolveArt = useLicensed ? licensedArt : art;
  const restingPortrait = resolveArt(companion.portrait);

  return {
    id: fallback.id,
    name: companion.label,
    artKey: companion.art_key,
    temporary: companion.temporary,
    portrait: restingPortrait,
    happyPortrait: resolveArt(companion.happy_portrait) || restingPortrait,
    blinkPortrait: resolveArt(companion.blink_portrait) || restingPortrait,
  };
}
