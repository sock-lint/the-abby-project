import { useState } from 'react';
import { Hammer } from 'lucide-react';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-forge-bg p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-amber-primary/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Hammer className="text-amber-highlight" size={32} />
          </div>
          <h1 className="font-heading text-2xl text-amber-highlight font-bold">The Abby Project</h1>
          <p className="text-forge-text-dim text-sm mt-1">Track projects, earn badges, get paid</p>
        </div>
        <form onSubmit={handleSubmit} className="bg-forge-card border border-forge-border rounded-xl p-6 space-y-4">
          {error && (
            <div className="text-red-400 text-sm bg-red-400/10 px-3 py-2 rounded-lg">{error}</div>
          )}
          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text focus:outline-none focus:border-amber-primary"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text focus:outline-none focus:border-amber-primary"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-amber-primary hover:bg-amber-highlight text-black font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
