/**
 * FolioHeadband — the woven cloth cap at the top of an open folio's verso,
 * carried over from the closed `TomeSpine` so a shelf and the spread it
 * opens onto share one binding vocabulary.
 *
 * Extracted from the identical blocks in `pages/quests/QuestFolio.jsx` and
 * `pages/achievements/FolioSpread.jsx` (the "reused twice" promotion rule
 * in components/README.md), and reworked because the original
 * `absolute top-0 left-0 right-0 h-1.5` slab misread on three counts:
 *
 *   - **It buried the corner flourishes.** `ParchmentCard`'s scrollwork
 *     sits at `top-1 left-1`, and its outer L-frame stroke lands ~5px
 *     from the card edge — inside a 6px band pinned at `top-0`. The top
 *     corners stopped matching the bottom ones. The band now starts
 *     inboard of that ink.
 *   - **The corner radius sliced it.** The card is `rounded-xl` with
 *     `overflow-hidden`, so a full-bleed band got cut by the 11px curve
 *     into a tapering wedge at each end. Ending inside the curve keeps
 *     both terminals finished.
 *   - **It read as chrome below `md`.** There the verso stops being a
 *     220-260px column and becomes a full-width banner, so 6px of flat
 *     color stretched the whole card width — a stalled progress bar
 *     rather than cloth. The weave and the trailing fade (see
 *     `.folio-headband` in index.css) are what sell it as fabric at that
 *     length.
 *
 * At `md+` the right terminal still runs to the gutter fold, because on a
 * two-page spread that fold *is* the binding edge.
 *
 * Decorative only — `aria-hidden`, no pointer events. Tier is exposed on
 * `data-tier` so tests can pin the vocabulary without asserting on hex.
 */

const HEADBAND_TONE = {
  locked: 'var(--color-headband-locked)',
  nascent: 'var(--color-headband-nascent)',
  rising: 'var(--color-headband-rising)',
  cresting: 'var(--color-headband-cresting)',
  gilded: 'var(--color-headband-gilded)',
};

export default function FolioHeadband({ tierKey = 'locked', className = '' }) {
  return (
    <span
      aria-hidden="true"
      data-folio-headband="true"
      data-tier={tierKey}
      className={`folio-headband absolute top-0 left-6 right-6 md:right-0 h-1.5 rounded-full pointer-events-none ${className}`}
      style={{
        backgroundColor: HEADBAND_TONE[tierKey] ?? HEADBAND_TONE.locked,
        // Alternating light/dark threads at 45° — the two-tone chevron is
        // the signature tell of a real hand-sewn headband, and it is what
        // keeps 6px of color reading as woven cloth once the band is
        // stretched across a phone-width card.
        backgroundImage:
          'repeating-linear-gradient(45deg, rgba(255, 248, 224, 0.34) 0 2px, rgba(45, 31, 21, 0.10) 2px 4px)',
        boxShadow:
          'inset 0 -1px 0 rgba(45, 31, 21, 0.28), inset 0 1px 0 rgba(255, 248, 224, 0.38)',
      }}
    />
  );
}
