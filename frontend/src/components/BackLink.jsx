import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export default function BackLink({ to, children }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1.5 text-caption text-ink-secondary hover:text-ink-primary transition-colors group"
    >
      <ArrowLeft
        size={14}
        className="transition-transform group-hover:-translate-x-0.5"
      />
      <span className="font-script">{children}</span>
    </Link>
  );
}
