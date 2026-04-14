import ParchmentCard from './journal/ParchmentCard';

/**
 * Card — thin wrapper delegating to ParchmentCard so legacy callers
 * automatically inherit the Hyrule Field Notes aesthetic without needing
 * to migrate import sites.
 */
export default function Card({ children, className = '', ...props }) {
  return (
    <ParchmentCard className={className} {...props}>
      {children}
    </ParchmentCard>
  );
}
