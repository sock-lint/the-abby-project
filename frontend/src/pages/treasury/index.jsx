import ChapterHub from '../../components/layout/ChapterHub';
import Payments from '../Payments';
import Timecards from '../Timecards';
import Rewards from '../Rewards';

/**
 * Treasury — hub page for "money and coins."
 *
 * Coffers (Payments) · Wages (Timecards) · Bazaar (Rewards)
 *
 * Note: Exchange and Hoard (Savings) are surfaced through Rewards / Today
 * in the current data model. Phase 4 may split them into their own tabs.
 */
export default function TreasuryHub() {
  return (
    <ChapterHub
      title="Treasury"
      kicker="Chapter IV · Coin, Wage & Market"
      glyph="wax-seal"
      defaultTabId="coffers"
      tabs={[
        { id: 'coffers', label: 'Coffers', render: () => <Payments /> },
        { id: 'wages',   label: 'Wages',   render: () => <Timecards /> },
        { id: 'bazaar',  label: 'Bazaar',  render: () => <Rewards /> },
      ]}
    />
  );
}
