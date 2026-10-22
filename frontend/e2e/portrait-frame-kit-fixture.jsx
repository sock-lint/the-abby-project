import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { applyTheme, themes } from '../src/themes';
import ProfilePortrait from '../src/components/identity/ProfilePortrait';
import Button from '../src/components/Button';

const parameters = new URLSearchParams(window.location.search);
const theme = parameters.get('theme');
applyTheme(Object.hasOwn(themes, theme) ? theme : 'hyrule');
const frames = [
  ['laurel', 'Laurel Wreath Frame'], ['steampunk', 'Steampunk Gear Frame'], ['rune-circle', 'Rune Circle Frame'],
  ['cosmic', 'Cosmic Frame'], ['scholar', 'Scholar Frame'], ['pixel', 'Pixel Pixel Frame'],
].map(([family, name]) => ({ slug: `frame-${family}`, name }));

// An original, synthetic image exercises the uploaded-picture branch without
// personal photos, external image requests, or household data.
const picture = document.createElement('canvas');
picture.width = 512;
picture.height = 512;
const context = picture.getContext('2d');
context.fillStyle = '#c8dce4';
context.fillRect(0, 0, 512, 512);
context.fillStyle = '#b99077';
context.beginPath(); context.ellipse(256, 268, 160, 205, 0, 0, 2 * Math.PI); context.fill();
context.fillStyle = '#594638';
context.beginPath(); context.ellipse(256, 143, 159, 88, 0, Math.PI, 2 * Math.PI); context.fill();
context.fillStyle = '#253e47';
for (const x of [199, 313]) { context.beginPath(); context.arc(x, 242, 15, 0, 2 * Math.PI); context.fill(); }
context.strokeStyle = '#74503e'; context.lineWidth = 9; context.lineCap = 'round';
context.beginPath(); context.moveTo(256, 270); context.lineTo(242, 310); context.lineTo(264, 310); context.stroke();
context.strokeStyle = '#854d4f';
context.beginPath(); context.arc(256, 331, 49, 0.2, Math.PI - 0.2); context.stroke();
const photoUrl = picture.toDataURL('image/png');

export default function Fixture() {
  const [photo, setPhoto] = useState(photoUrl);
  const [density, setDensity] = useState();
  return <main className="mx-auto max-w-6xl space-y-6 bg-ink-page p-4 text-ink-primary">
    <h1 className="font-body text-2xl font-bold">Private portrait frame acceptance</h1>
    <div className="flex flex-wrap gap-3">
      <Button onClick={() => setPhoto('/synthetic/unavailable-picture.png')}>Use unavailable picture</Button>
      <Button onClick={() => setPhoto(photoUrl)}>Restore picture</Button>
      <Button onClick={() => setDensity((previous) => (previous ?? Math.min(3, Math.ceil(window.devicePixelRatio))) === 1 ? 2 : 1)}>Use alternate density</Button>
    </div>
    {[32, 40, 64, 96].map((size) => <section key={size} aria-label={`${size}px portraits`} className="space-y-3">
      <h2 className="font-body text-xl font-bold">{size}px portraits</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {frames.map((frame) => <figure key={frame.slug} data-kit-example={frame.slug} className="flex flex-col items-center gap-3 rounded-2xl border border-ink-page-shadow p-3">
          <figcaption className="font-body text-center text-caption font-semibold">{frame.name}</figcaption>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <span data-picture-kind="initial"><ProfilePortrait name="Alex Maker" frame={frame} size={size} devicePixelRatio={density} /></span>
            <span data-picture-kind="photo"><ProfilePortrait name="Alex Maker" avatar={photo} frame={frame} size={size} devicePixelRatio={density} /></span>
          </div>
        </figure>)}
      </div>
    </section>)}
    <section aria-label="Unreviewed canvas sizes" className="flex flex-wrap gap-4">
      {[80, 128, 256].map((size) => <ProfilePortrait key={size} name="Alex Maker" frame={frames[0]} size={size} />)}
    </section>
  </main>;
}

createRoot(document.getElementById('root')).render(<Fixture />);
