import { useState } from 'react';
import { api } from '../api/client';
import Card from '../components/Card';
import { themes, applyTheme } from '../themes';

export default function SettingsPage({ user }) {
  const [currentTheme, setCurrentTheme] = useState(user?.theme || 'summer');

  const handleThemeChange = async (themeName) => {
    setCurrentTheme(themeName);
    applyTheme(themeName);
    try {
      await api.patch(`/auth/me/`, { theme: themeName });
    } catch {}
  };

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
        <h2 className="font-heading text-lg font-bold mb-4">Theme</h2>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(themes).map(([key, theme]) => (
            <button
              key={key}
              onClick={() => handleThemeChange(key)}
              className={`p-3 rounded-xl border-2 text-left transition-all ${
                currentTheme === key
                  ? 'border-amber-primary'
                  : 'border-forge-border hover:border-forge-muted'
              }`}
              style={{ backgroundColor: theme.bg }}
            >
              <div className="text-2xl mb-1">{theme.icon}</div>
              <div className="text-sm font-medium" style={{ color: theme.highlight }}>
                {theme.name}
              </div>
              <div className="flex gap-1 mt-2">
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: theme.primary }} />
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: theme.highlight }} />
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: theme.glow }} />
              </div>
            </button>
          ))}
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
