import PedestalImage from '../../pedestal/PedestalImage';
import { cardStyleForFrame } from './cardStylePresentation';
import './profile-card-styles.css';

/** Complete decorative canvas; real badge/frame identity stays beside it. */
export default function CardStyleArtwork({ frame, className = '' }) {
  const style = cardStyleForFrame(frame);
  if (!style) return null;
  return <span aria-hidden="true" data-profile-card-art="true" className={`profile-card-style-art ${className}`}>
    <PedestalImage assetId={style.assetId} fallback="" />
  </span>;
}
