import { useContext, useState } from 'react';
import SectionHeader from '../../components/SectionHeader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { CheckboxField, SelectField } from '../../components/form';
import PedestalImage from '../../pedestal/PedestalImage';
import PedestalFrame from '../../pedestal/PedestalFrame';
import PedestalPreview from '../../pedestal/PedestalPreview';
import StorybookFeature from '../../pedestal/StorybookFeature';
import StarRating from '../../components/StarRating';
import { PEDESTAL_EGG_IDS, PEDESTAL_IMAGE_IDS } from '../../pedestal/pedestalRelease';
import { DesignPreviewContext } from './preview.context';

const modelNames = {
  'normal-egg': 'Normal Egg · static',
  'legendary-egg': 'Legendary Egg · static',
  'legendary-egg-idle-breath': 'Legendary Egg · IdleBreath',
  'legendary-egg-idle-wobble': 'Legendary Egg · IdleWobble',
  'legendary-egg-hatching-soon': 'Legendary Egg · HatchingSoon',
};
const imageName = id => id.split('-').map(part => `${part[0].toUpperCase()}${part.slice(1)}`).join(' ');

export default function PedestalShowcase() {
  const [eggAssetId, setEggAssetId] = useState('normal-egg');
  const [animate, setAnimate] = useState(true);
  const [imageId, setImageId] = useState('card-front-egg-star');
  const [variantId, setVariantId] = useState('web');
  const [gallery, setGallery] = useState(false);
  const { longContent } = useContext(DesignPreviewContext);
  return <section id="design-pedestal" aria-label="Pedestal and card artwork" className="space-y-3 scroll-mt-4">
    <SectionHeader title="Pedestal and card artwork" kicker="Private release preview" />
    <p className="text-body text-ink-secondary">Local artwork choices. These previews do not change ownership, pet appearances, rarity or hatch outcomes.</p>
    <ParchmentCard flourish className="space-y-3">
      <h3 className="font-bold text-lede">Storybook accents</h3>
      <p className="text-body text-ink-secondary">Simple rounded panels keep the focus on content. Larger illustrations stack when the card has limited room, keeping text and controls clear.</p>
      <StorybookFeature assetId="card-front-light">
        <h4 className="font-bold text-body">{longContent ? 'Make a paper kite with a decorated tail and a sturdy frame for the whole family to try outdoors' : 'Make a paper kite'}</h4>
        <div className="mt-2 flex flex-wrap items-center gap-1 text-caption text-ink-secondary"><span aria-hidden="true">Difficulty:</span><StarRating value={3} /></div>
        <p className="mt-2 text-body text-ink-secondary">Real activity details stay separate from decorative card faces.</p>
      </StorybookFeature>
    </ParchmentCard>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ParchmentCard className="space-y-3 min-w-0">
        <h3 className="font-bold text-lede">Native model takes</h3>
        <SelectField label="Egg artwork" value={eggAssetId} onChange={event => setEggAssetId(event.target.value)}>
          <option value="">Pedestal only · PlantLoop</option>
          {PEDESTAL_EGG_IDS.map(id => <option key={id} value={id}>{modelNames[id]}</option>)}
        </SelectField>
        <CheckboxField label="Play native loops" checked={animate} onChange={event => setAnimate(event.target.checked)} />
        <div data-pedestal-scene-selection={eggAssetId || 'pedestal-only'}>
          <PedestalPreview eggAssetId={eggAssetId || null} animate={animate} />
        </div>
        <p className="text-caption text-ink-secondary">PlantLoop belongs to the pedestal. Each animated egg keeps its own mesh and rig. HatchingSoon repeats anticipation; it does not complete a hatch or grant a reward.</p>
      </ParchmentCard>
      <ParchmentCard className="space-y-3 min-w-0">
        <h3 className="font-bold text-lede">Complete card canvases</h3>
        <SelectField label="UI artwork" value={imageId} onChange={event => setImageId(event.target.value)}>
          {PEDESTAL_IMAGE_IDS.map(id => <option key={id} value={id}>{imageName(id)}</option>)}
        </SelectField>
        <SelectField label="Selected image resolution" value={variantId} onChange={event => setVariantId(event.target.value)} helpText="Default web images are 512px. Select native deliberately for a large display or device pixel ratio; the three 512px originals keep their web variant.">
          <option value="web">Web · 512px</option>
          <option value="native">Native · up to 1024px</option>
        </SelectField>
        <figure className="max-w-sm mx-auto">
          <PedestalImage assetId={imageId} variantId={variantId} alt={imageName(imageId)} />
          <figcaption className="text-caption text-ink-secondary text-center">{imageName(imageId)}</figcaption>
        </figure>
        <p className="text-caption text-ink-secondary">Faces already include their emblems. Transparent margins, native proportions and source alpha remain intact.</p>
      </ParchmentCard>
    </div>
    <ParchmentCard className="space-y-3">
      <h3 className="font-bold text-lede">Gold frame opening</h3>
      <p className="text-body text-ink-secondary">The measured opening holds independent app content with padding. Enlarged or long text remains scrollable inside the frame.</p>
      <PedestalFrame className="max-w-sm mx-auto">
        <h4 className="font-bold text-body">{longContent ? 'A very long example heading that stays inside the measured frame opening' : 'Artwork example'}</h4>
        <p className="mt-3 text-body">{longContent ? 'This independent application content preserves the entire authored border. Long names and larger text can be read by scrolling the frame opening, without stretching or cropping the PNG.'.repeat(3) : 'A proportional frame around readable application content.'}</p>
      </PedestalFrame>
    </ParchmentCard>
    <CheckboxField label="Show all 19 web images" checked={gallery} onChange={event => setGallery(event.target.checked)} />
    {gallery && <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-3" data-pedestal-image-gallery="true">
      {PEDESTAL_IMAGE_IDS.map(id => <figure key={id} className="min-w-0 rounded-xl border border-ink-page-shadow p-3">
        <PedestalImage assetId={id} alt={imageName(id)} />
        <figcaption className="text-caption text-ink-secondary break-words">{imageName(id)}</figcaption>
      </figure>)}
    </div>}
    <details className="rounded-lg border border-ink-page-shadow px-3 text-body text-ink-secondary">
      <summary className="min-h-11 flex items-center cursor-pointer">Usage and existing consumers</summary>
      <p className="mb-3">Hatching uses a neutral Normal Egg and pedestal as decoration beside its existing ingredient controls. Other styles are review choices here; they have no catalog binding. Paid files are available only through the private staged release.</p>
      <pre className="whitespace-pre-wrap break-all text-caption">{'import PedestalImage from "../../pedestal/PedestalImage";\nimport PedestalFrame from "../../pedestal/PedestalFrame";\nimport PedestalPreview from "../../pedestal/PedestalPreview";'}</pre>
      <a href="/bestiary?tab=hatchery" className="min-h-11 inline-flex items-center underline">Hatching</a>
    </details>
  </section>;
}
