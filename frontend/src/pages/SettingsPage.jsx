import Card from '../components/Card';

export default function SettingsPage({ user }) {
  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="font-heading text-2xl font-bold">Settings</h1>

      <Card>
        <h2 className="font-heading text-lg font-bold mb-4">Profile</h2>
        <div className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Username</span>
            <span>{user?.username}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Display Name</span>
            <span>{user?.display_name || '—'}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Role</span>
            <span className="capitalize">{user?.role}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Hourly Rate</span>
            <span className="font-heading font-bold">${user?.hourly_rate}/hr</span>
          </div>
        </div>
      </Card>

      <Card>
        <h2 className="font-heading text-lg font-bold mb-2">About SummerForge</h2>
        <p className="text-sm text-forge-text-dim">
          Track projects, log hours, earn XP, unlock skills, and get paid
          for your summer maker projects.
        </p>
      </Card>
    </div>
  );
}
