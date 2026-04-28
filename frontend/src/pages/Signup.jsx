import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import Button from '../components/Button';
import ErrorAlert from '../components/ErrorAlert';
import { TextField } from '../components/form';
import ParchmentCard from '../components/journal/ParchmentCard';

/**
 * Signup — found a new family. Mirrors Login's parchment-cover aesthetic;
 * on success the AuthProvider has already stashed the token + user, so we
 * just navigate to the dashboard. On 403 we swap the form for a "sealed"
 * empty state so the user knows signup was disabled at deploy time.
 */
export default function Signup({ onSignup }) {
  const navigate = useNavigate();
  const [familyName, setFamilyName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [disabled, setDisabled] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onSignup({
        username,
        password,
        display_name: displayName,
        family_name: familyName,
      });
      navigate('/', { replace: true });
    } catch (err) {
      if (err?.status === 403) {
        setDisabled(true);
        return;
      }
      setError(err?.message || 'Could not create your family.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 parchment-bg">
      <div className="w-full max-w-sm">
        <div className="text-center mb-5">
          <div className="font-script text-sheikah-teal-deep text-base">
            found a new household
          </div>
          <h1 className="font-display italic text-3xl text-ink-primary leading-tight">
            Hyrule Field Notes
          </h1>
        </div>

        {disabled ? (
          <ParchmentCard flourish>
            <div className="space-y-4 text-center">
              <h2 className="font-display italic text-xl text-ink-primary">
                Signup is sealed.
              </h2>
              <p className="font-body text-ink-secondary text-sm">
                New families can&apos;t be founded on this codex right now.
              </p>
              <Link
                to="/login"
                className="block font-script text-sheikah-teal-deep text-xs hover:underline"
              >
                Back to sign in
              </Link>
            </div>
          </ParchmentCard>
        ) : (
          <ParchmentCard flourish as="form" onSubmit={handleSubmit}>
            <div className="space-y-4">
              <ErrorAlert message={error} />
              <TextField
                id="signup-family"
                label="What is this family called?"
                type="text"
                value={familyName}
                onChange={(e) => setFamilyName(e.target.value)}
                autoFocus
                required
                maxLength={120}
              />
              <TextField
                id="signup-display"
                label="Your name as the head scribe"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                autoComplete="name"
              />
              <TextField
                id="signup-username"
                label="Choose a sign-in name"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
              />
              <TextField
                id="signup-password"
                label="Choose a secret word"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
              />
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? 'Founding…' : 'Found a family'}
              </Button>
              <Link
                to="/login"
                className="block text-center font-script text-sheikah-teal-deep text-xs hover:underline"
              >
                Have an account? Sign in
              </Link>
            </div>
          </ParchmentCard>
        )}
      </div>
    </div>
  );
}
