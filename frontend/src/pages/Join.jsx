import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';

import Button from '../components/Button';
import IconButton from '../components/IconButton';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import { TextField } from '../components/form';
import ParchmentCard from '../components/journal/ParchmentCard';
import { getJoinInvite } from '../api';
import { useApi } from '../hooks/useApi';

/**
 * Join — redeem a co-parent invite link (/join/<token>). Mirrors Signup's
 * parchment-cover aesthetic. The invite is previewed first so the page
 * can say WHOSE family you're joining before asking for credentials;
 * invalid/expired/used tokens all collapse to one sealed empty state
 * (the backend deliberately doesn't say which).
 */
export default function Join({ onJoin }) {
  const navigate = useNavigate();
  const { token } = useParams();
  const { data: invite, loading: previewLoading, error: previewError } = useApi(
    () => getJoinInvite(token),
    [token],
  );
  const [displayName, setDisplayName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!username.trim()) {
      setError('Choose a sign-in name to continue.');
      return;
    }
    if (!password) {
      setError('Choose a secret word to continue.');
      return;
    }
    setLoading(true);
    try {
      await onJoin(token, {
        username,
        password,
        display_name: displayName,
      });
      navigate('/', { replace: true });
    } catch (err) {
      setError(err?.message || 'Could not join the family.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 parchment-bg">
      <div className="w-full max-w-sm">
        <div className="text-center mb-5">
          <div className="font-script text-sheikah-teal-deep text-base">
            you&apos;ve been invited
          </div>
          <h1 className="font-display italic text-3xl text-ink-primary leading-tight">
            Hyrule Field Notes
          </h1>
        </div>

        {previewLoading ? (
          <Loader />
        ) : previewError || !invite ? (
          <ParchmentCard flourish>
            <div className="space-y-4 text-center">
              <h2 className="font-display italic text-xl text-ink-primary">
                This invite is sealed.
              </h2>
              <p className="font-body text-ink-secondary text-sm">
                The link is invalid, was already used, or has expired. Ask
                your co-parent to send a fresh one.
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
              <p className="font-script text-ink-secondary text-body text-center">
                {invite.invited_by} invited you to join the{' '}
                <span className="text-ink-primary font-semibold">
                  {invite.family_name}
                </span>{' '}
                family as a co-parent.
              </p>
              <ErrorAlert message={error} />
              <TextField
                id="join-display"
                label="Your name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="How the family sees you"
                autoComplete="name"
              />
              <TextField
                id="join-username"
                label="Sign-in name"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Your username"
                autoComplete="username"
              />
              <div className="relative">
                <TextField
                  id="join-password"
                  label="Secret word"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                />
                <IconButton
                  size="sm"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-2 bottom-1.5"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </IconButton>
              </div>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? 'Joining…' : 'Join the family'}
              </Button>
              <Link
                to="/login"
                className="block text-center font-script text-sheikah-teal-deep text-xs hover:underline"
              >
                Already have an account? Sign in
              </Link>
            </div>
          </ParchmentCard>
        )}
      </div>
    </div>
  );
}
