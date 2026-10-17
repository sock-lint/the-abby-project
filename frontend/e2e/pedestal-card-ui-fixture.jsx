import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { Box3, Vector3 } from 'three';
import Button from '../src/components/Button';
import DesignEnvironment from '../src/pages/design/DesignEnvironment';
import PedestalShowcase from '../src/pages/design/PedestalShowcase';
import Hatchery from '../src/pages/bestiary/hatchery/Hatchery';
import PedestalPreview from '../src/pedestal/PedestalPreview';
import PedestalImage from '../src/pedestal/PedestalImage';
import { stagedPedestalRelease } from '../src/pedestal/pedestalRelease';
import { createPedestalPlayback, PEDESTAL_EGG_ASSETS, PEDESTAL_SUPPORT_ANCHOR } from '../src/pedestal/pedestalPlayback';
import '../src/index.css';

// This fixture imports the real current-app loader/playback. The probe is kept
// outside production components: no test global or instrumentation ships there.
async function inspectNativeModels() {
  const staged = stagedPedestalRelease();
  if (!staged) throw new Error('Private pinned release is absent.');
  const entries = [];
  for (const eggAssetId of [null, ...PEDESTAL_EGG_ASSETS]) {
    let failure;
    const playback = createPedestalPlayback(staged, {
      eggAssetId, position: [1.2, -0.3, 0.5], scale: 0.37, rotationY: 0.41,
      onError: error => { failure = error.message; },
    });
    try {
      if (!await playback.ready) throw new Error(failure || 'Native model loading failed.');
      const { root } = playback;
      root.updateMatrixWorld(true);
      const placement = root.getObjectByName('PedestalEggPlacement');
      const worldAnchor = new Vector3(...PEDESTAL_SUPPORT_ANCHOR).applyMatrix4(root.matrixWorld);
      const worldPlacement = placement?.getWorldPosition(new Vector3());
      const inverse = root.matrixWorld.clone().invert();
      const pedestal = root.children.find(child => child !== placement);
      const egg = placement?.children[0];
      const nativeNames = [];
      const counts = { skinnedMeshes: 0, meshes: 0, vertices: 0 };
      root.traverse(node => {
        if (node.isMesh) {
          counts.meshes += 1;
          counts.vertices += node.geometry.attributes.position.count;
          if (node.isSkinnedMesh) counts.skinnedMeshes += 1;
        }
        if (node.isBone) nativeNames.push(node.name);
      });
      const point = new Vector3();
      let allFinite = true;
      const readVertices = (object, visit) => object?.traverse(node => {
        if (!node.isMesh) return;
        node.skeleton?.update();
        for (let index = 0; index < node.geometry.attributes.position.count; index += 1) {
          node.getVertexPosition(index, point).applyMatrix4(node.matrixWorld).applyMatrix4(inverse);
          if (![point.x, point.y, point.z].every(Number.isFinite)) allFinite = false;
          visit(point);
        }
      });
      const highestIntersectingTriangle = bounds => {
        let highest = -Infinity;
        pedestal.traverse(node => {
          if (!node.isMesh) return;
          node.skeleton?.update();
          const vertices = [];
          for (let index = 0; index < node.geometry.attributes.position.count; index += 1) {
            node.getVertexPosition(index, point).applyMatrix4(node.matrixWorld).applyMatrix4(inverse);
            if (![point.x, point.y, point.z].every(Number.isFinite)) allFinite = false;
            vertices.push(point.clone());
          }
          const index = node.geometry.index;
          const count = index?.count || vertices.length;
          for (let offset = 0; offset < count; offset += 3) {
            const triangle = [0, 1, 2].map(corner => vertices[index ? index.getX(offset + corner) : offset + corner]);
            // A triangle can cross the egg envelope while all three vertices
            // lie outside it. Include every overlapping triangle's complete
            // upper extent; this deliberately overestimates possible contact.
            if (Math.max(...triangle.map(vertex => vertex.x)) < bounds.min.x - 0.01
              || Math.min(...triangle.map(vertex => vertex.x)) > bounds.max.x + 0.01
              || Math.max(...triangle.map(vertex => vertex.z)) < bounds.min.z - 0.01
              || Math.min(...triangle.map(vertex => vertex.z)) > bounds.max.z + 0.01) continue;
            highest = Math.max(highest, ...triangle.map(vertex => vertex.y));
          }
        });
        return highest;
      };
      const initial = new Box3();
      let maxDisplacement = 0;
      let minimumClearance = Infinity;
      let minimumSurroundingClearance = Infinity;
      let maximumEggRadius = 0;
      let samples = 0;
      let initialSignature;
      // Five seconds covers PlantLoop. Twenty covers every relative phase of
      // the five-second pedestal and 4/3-second breath/wobble loops (LCM 20s).
      // Every posed vertex is inspected at 60Hz, including each skin influence.
      const duration = /idle-breath|idle-wobble/.test(eggAssetId || '') ? 20 : 5;
      for (let frame = 0; frame <= duration * 60; frame += 1) {
        if (frame) playback.update(1 / 60, { active: true, paused: false, maxDelta: 0.05 });
        root.updateMatrixWorld(true);
        const eggBounds = new Box3();
        let signature = 0;
        readVertices(egg || pedestal, vertex => {
          eggBounds.expandByPoint(vertex);
          if (egg) maximumEggRadius = Math.max(maximumEggRadius, Math.hypot(vertex.x, vertex.z));
          signature += vertex.x * 0.31 + vertex.y * 0.53 + vertex.z * 0.73;
        });
        if (!frame) { initial.copy(eggBounds); initialSignature = signature; }
        maxDisplacement = Math.max(maxDisplacement, Math.abs(signature - initialSignature));
        if (egg) {
          minimumClearance = Math.min(minimumClearance, eggBounds.min.y - PEDESTAL_SUPPORT_ANCHOR[1]);
          const highestUnderEgg = highestIntersectingTriangle(eggBounds);
          minimumSurroundingClearance = Math.min(minimumSurroundingClearance, eggBounds.min.y - highestUnderEgg);
        }
        samples += 1;
        if (frame % 60 === 0) await new Promise(resolve => setTimeout(resolve, 0));
      }
      entries.push({
        assetId: eggAssetId || 'trunk-pedestal', allFinite, ...counts,
        bones: nativeNames.length, samples, duration, maxDisplacement,
        initialHeight: initial.max.y - initial.min.y,
        minimumClearance: egg ? minimumClearance : null,
        minimumSurroundingClearance: egg ? minimumSurroundingClearance : null,
        maximumEggRadius: egg ? maximumEggRadius : null,
        worldAnchor: worldAnchor.toArray(),
        worldPlacement: worldPlacement?.toArray() || null,
        rootScale: root.scale.toArray(),
      });
    } finally { playback.dispose(); }
  }
  return { manifestSha256: staged.manifestSha256, entries };
}

export function Probe() {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { setResult(await inspectNativeModels()); }
    catch (error) { setResult({ error: error.message }); }
    finally { setBusy(false); }
  };
  return <main className="p-4"><Button onClick={run} disabled={busy}>Inspect current native playback</Button>
    <pre data-native-probe-result={busy ? 'running' : result ? 'complete' : 'idle'}>{JSON.stringify(result)}</pre></main>;
}

export function Images() {
  const staged = stagedPedestalRelease();
  return <main className="grid grid-cols-3 gap-3 p-4">{staged?.release.assets.filter(asset => asset.kind === 'image').flatMap(asset => asset.variants.map(variant =>
    <figure key={`${asset.id}:${variant.id}`}><PedestalImage assetId={asset.id} variantId={variant.id} alt={`${asset.id} ${variant.id}`} /></figure>))}</main>;
}

const mode = new URLSearchParams(window.location.search).get('mode');
createRoot(document.getElementById('root')).render(<MemoryRouter>
  {mode === 'probe' ? <Probe /> : mode === 'images' ? <Images />
    : mode === 'fallback' ? <main className="p-4"><PedestalPreview staged={null} /><Button>Existing hatch controls</Button></main>
      : mode === 'hatchery' ? <main className="max-w-5xl p-4 mx-auto"><Hatchery /></main>
        : <DesignEnvironment><PedestalShowcase /></DesignEnvironment>}
</MemoryRouter>);
