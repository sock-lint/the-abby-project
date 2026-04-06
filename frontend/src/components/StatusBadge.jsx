const colors = {
  draft: 'bg-gray-500/20 text-gray-400',
  active: 'bg-blue-500/20 text-blue-400',
  in_progress: 'bg-amber-500/20 text-amber-400',
  in_review: 'bg-purple-500/20 text-purple-400',
  completed: 'bg-green-500/20 text-green-400',
  archived: 'bg-gray-500/20 text-gray-500',
  pending: 'bg-yellow-500/20 text-yellow-400',
  approved: 'bg-green-500/20 text-green-400',
  paid: 'bg-emerald-500/20 text-emerald-400',
  disputed: 'bg-red-500/20 text-red-400',
  voided: 'bg-red-500/20 text-red-500',
};

const labels = {
  in_progress: 'In Progress',
  in_review: 'In Review',
};

export default function StatusBadge({ status }) {
  const color = colors[status] || 'bg-gray-500/20 text-gray-400';
  const label = labels[status] || status?.charAt(0).toUpperCase() + status?.slice(1);
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
