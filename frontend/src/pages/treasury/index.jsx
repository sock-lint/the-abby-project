import ChapterHub from '../../components/layout/ChapterHub';
import Payments from '../Payments';
import Timecards from '../Timecards';
import Rewards from '../Rewards';
import HoardsTab from './HoardsTab';

/**
 * Treasury — hub page for "money and coins."
 *
 * Coffers (Payments) · Wages (Timecards) · Bazaar (Rewards) · Hoards (Savings)
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
        { id: 'hoards',  label: 'Hoards',  render: () => <HoardsTab /> },
      ]}
    />
  );
}
