import { STATUS_COLORS, STATUS_LABELS } from '../constants/colors';

export default function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || 'bg-gray-500/20 text-gray-400';
  const label = STATUS_LABELS[status] || status?.charAt(0).toUpperCase() + status?.slice(1);
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
