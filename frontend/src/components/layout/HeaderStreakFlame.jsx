import { useState } from 'react';
import { CircleHelp } from 'lucide-react';
import { resolveStreakFlame } from '../../streak/streakFlameRelease';

/** The complete authored canvas stays static. Each SVG image is an isolated
 * document, so its original gradient IDs cannot collide with another instance. */
export default function HeaderStreakFlame({ stage = 'unknown', size = 24 }) {
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const image = resolveStreakFlame(stage);
  const ready = image && !failedUrls.has(image.url);
  const canvasSize = size === 20 ? 20 : 24;
  return (
    <span
      data-header-streak-flame=""
      data-state={stage}
      data-artwork-status={ready ? 'ready' : 'unavailable'}
      className="inline-flex shrink-0 items-center justify-center"
      style={{ width: canvasSize, height: canvasSize }}
      aria-hidden="true"
    >
      {ready ? (
        <img
          src={image.url}
          alt=""
          width={canvasSize}
          height={canvasSize}
          className="block"
          onError={() => setFailedUrls((previous) => new Set([...previous, image.url]))}
        />
      ) : <CircleHelp size={canvasSize} />}
    </span>
  );
}
