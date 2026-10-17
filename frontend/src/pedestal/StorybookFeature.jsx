import PedestalImage from './PedestalImage';
import './storybook-feature.css';

/** Complete card artwork sits beside readable app content. It is decoration,
 * independent of a goal's rewards, rarity or catalog identity. */
export default function StorybookFeature({ assetId, children }) {
  return <div className="storybook-feature">
    {assetId && <div className="storybook-feature__art" data-storybook-card-art="true" aria-hidden="true">
      <PedestalImage assetId={assetId} fallback="" />
    </div>}
    <div className="storybook-feature__content" data-storybook-card-content="true">{children}</div>
  </div>;
}
