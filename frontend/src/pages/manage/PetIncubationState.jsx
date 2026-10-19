const metrics = [['incubating_eggs', 'Eggs incubating'], ['ready_eggs', 'Ready eggs awaiting hatch']];
const quantiles = ['p10', 'p50', 'p90'];
const count = (value) => Number.isFinite(value) && value >= 0
  ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value) : 'Unrecorded';

export default function PetIncubationState({ snapshot }) {
  const day = Number.isFinite(snapshot?.day) ? `Day ${snapshot.day}` : 'Day unrecorded';
  const recorded = metrics.some(([key]) => quantiles.some((quantile) => Number.isFinite(snapshot?.[`${key}_${quantile}`])));
  return <section aria-label="Eggs awaiting hatching" className="space-y-2">
    <h4 className="font-semibold text-ink-primary">Eggs awaiting hatching</h4>
    {!recorded && <p role="status" className="text-body text-ink-secondary">Incubation counts were not recorded for this day.</p>}
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Incubation state percentiles, horizontally scrollable">
      <table className="w-full text-body text-left">
        <caption className="sr-only">{day} incubation state across simulated children</caption>
        <thead><tr><th className="p-2">Egg state</th><th className="p-2">10th percentile</th><th className="p-2">Median</th><th className="p-2">90th percentile</th></tr></thead>
        <tbody>{metrics.map(([key, label]) => <tr key={key} className="border-t border-ink-page-shadow">
          <th scope="row" className="p-2 font-semibold">{label}</th>
          {quantiles.map((quantile) => <td className="p-2" key={quantile}>{count(snapshot?.[`${key}_${quantile}`])}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
    <p className="text-caption text-ink-secondary">Incubating eggs are still waiting; ready eggs await a hatch claim. Percentiles in different rows can describe different simulated children. The hatch claim adds the companion milestone.</p>
  </section>;
}
