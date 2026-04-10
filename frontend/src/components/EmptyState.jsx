import Card from './Card';

export default function EmptyState({ children, className = '' }) {
  return (
    <Card className={`text-center py-12 text-forge-text-dim ${className}`}>
      {children}
    </Card>
  );
}
