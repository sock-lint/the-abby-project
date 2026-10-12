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
      title="Rewards"
      kicker="Track earnings, spend coins, and set savings goals"
      glyph="wax-seal"
      defaultTabId="coffers"
      tabs={[
        { id: 'coffers', label: 'Payments', render: () => <Payments /> },
        { id: 'wages',   label: 'Timecards', render: () => <Timecards /> },
        { id: 'bazaar',  label: 'Shop', render: () => <Rewards /> },
        { id: 'satchel', label: 'Inventory', render: () => <Inventory /> },
        { id: 'hoards',  label: 'Savings goals', render: () => <HoardsTab /> },
      ]}
    />
  );
}
