import ChapterHub from '../../components/layout/ChapterHub';
import Payments from '../Payments';
import Timecards from '../Timecards';
import Rewards from '../Rewards';
import HoardsTab from './HoardsTab';
import Inventory from '../Inventory';

/**
 * Treasury — hub page for "money, coins, and the things they buy or fall as."
 *
 * Coffers (Payments) · Wages (Timecards) · Bazaar (Rewards) · Hoards (Savings)
 *   · Satchel (Inventory — drops, cosmetics, consumables)
 */
export default function TreasuryHub() {
  return (
    <ChapterHub
      title="Treasury"
      kicker="Chapter IV · Coin, Wage, Market & Satchel"
      glyph="wax-seal"
      defaultTabId="coffers"
      tabs={[
        { id: 'coffers', label: 'Coffers', render: () => <Payments /> },
        { id: 'wages',   label: 'Wages',   render: () => <Timecards /> },
        { id: 'bazaar',  label: 'Bazaar',  render: () => <Rewards /> },
        { id: 'satchel', label: 'Satchel', render: () => <Inventory /> },
        { id: 'hoards',  label: 'Hoards',  render: () => <HoardsTab /> },
      ]}
    />
  );
}
