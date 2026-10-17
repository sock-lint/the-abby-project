const CARD_STYLES = {
  'card-front-nature': { label: 'Nature card style' },
  'card-front-light': { label: 'Light card style' },
};

// Django projects this field for supported frame rewards. Names, rarity and
// local artwork never establish ownership.
export function cardStyleForFrame(frame) {
  const assetId = frame?.metadata?.card_asset_id;
  return Object.hasOwn(CARD_STYLES, assetId) ? { assetId, ...CARD_STYLES[assetId] } : null;
}
