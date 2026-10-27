import { useSpace } from '../../hooks/useSpace';
import ChapterHub from '../../components/layout/ChapterHub';
import Payments from '../Payments';
import Timecards from '../Timecards';
import Rewards from '../Rewards';
import HoardsTab from './HoardsTab';
import Inventory from '../Inventory';
import Forge from '../forge';

/**
 * Treasury — hub page for "money, coins, and the things they buy or fall as."
 *
 * Coffers (Payments) · Wages (Timecards) · Bazaar (Rewards) · Hoards (Savings)
 *   · Satchel (Inventory — drops, cosmetics, consumables)
 */
export default function TreasuryHub() {
  const { isParentAccount, isPersonalSpace, isFamilySpace } = useSpace();
  const personalParent = isParentAccount && isPersonalSpace;
  return (
    <ChapterHub
      title="Rewards"
      kicker={personalParent ? 'Spend your coins and manage your collection' : 'Track earnings, spend coins, and set savings goals'}
      glyph="wax-seal"
      defaultTabId={personalParent ? 'bazaar' : 'coffers'}
      tabs={[
        ...(!personalParent ? [
          { id: 'coffers', label: 'Payments', render: () => <Payments /> },
          { id: 'wages', label: 'Timecards', render: () => <Timecards /> },
        ] : []),
        { id: 'bazaar',  label: 'Shop', render: () => <Rewards /> },
        ...(!personalParent ? [{ id: 'forge', label: '3D Prints', render: () => <Forge /> }] : []),
        ...(!isFamilySpace ? [
          { id: 'satchel', label: 'Inventory', render: () => <Inventory /> },
          { id: 'hoards', label: 'Savings goals', render: () => <HoardsTab /> },
        ] : []),
      ]}
    />
  );
}
