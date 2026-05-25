import { Check, Clock, X, AlertTriangle, Archive, Eye } from 'lucide-react';
import { STATUS_COLORS, STATUS_LABELS } from '../constants/colors';

const STATUS_ICONS = {
  completed: Check,
  approved: Check,
  fulfilled: Check,
  paid: Check,
  pending: Clock,
  in_review: Eye,
  in_progress: Clock,
  denied: X,
  voided: X,
  failed: X,
  canceled: X,
  expired: Archive,
  disputed: AlertTriangle,
};

export default function StatusBadge({ status, showIcon = true }) {
  const color = STATUS_COLORS[status] || 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30';
  const label = STATUS_LABELS[status] || status?.charAt(0).toUpperCase() + status?.slice(1);
  const Icon = showIcon ? STATUS_ICONS[status] : null;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-caption font-medium ${color}`}>
      {Icon && <Icon size={12} aria-hidden="true" />}
      {label}
    </span>
  );
}
