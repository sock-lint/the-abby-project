import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { applyTheme } from '../src/themes';
import HeaderStreakFlame from '../src/components/layout/HeaderStreakFlame';
import { resolveStreakFlame } from '../src/streak/streakFlameRelease';

const parameters = new URLSearchParams(window.location.search);
const theme = parameters.get('theme') === 'vigil' ? 'vigil' : 'hyrule';
const grayscale = parameters.get('grayscale') === '1';
applyTheme(theme);
const stages = ['dormant-ember', 'small-flame', 'strong-flame', 'maximum-blaze'];

export default function Fixture() {
  return <main className="min-h-screen bg-ink-page p-4 text-ink-primary space-y-4">
    <h1 className="text-lede font-bold">Private streak flame acceptance</h1>
    <p className="text-caption">{theme} · {grayscale ? 'Grayscale' : 'Original colors'} · complete authored canvases</p>
    <div data-flame-grid="" style={grayscale ? { filter: 'grayscale(1)' } : undefined} className="space-y-4">
      {[20, 24].map((size) => <section key={size} aria-label={`${size}px flame stages`} className="space-y-3">
        <h2 className="text-body font-bold">{size}px</h2>
        <div className="flex flex-wrap items-end gap-4">
          {stages.map((stage) => {
            const image = resolveStreakFlame(stage);
            return <figure key={stage} data-flame-example={stage} data-flame-size={size}
              data-release-family={image?.family_id} data-release-version={image?.release_version}
              data-release-manifest={image?.manifest_sha256} data-release-sha256={image?.sha256}
              className="space-y-2">
              <figcaption className="text-caption">{stage}</figcaption>
              <div className="flex items-end gap-3">
                <HeaderStreakFlame stage={stage} size={size} />
                <HeaderStreakFlame stage={stage} size={size} />
              </div>
            </figure>;
          })}
        </div>
      </section>)}
    </div>
    <section aria-label="Unknown bonus" className="space-y-2">
      <h2 className="text-body font-bold">Bonus unavailable</h2>
      <HeaderStreakFlame stage="unknown" />
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<Fixture />);
