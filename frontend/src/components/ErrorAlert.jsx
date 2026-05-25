import Button from './Button';

// Ember-tinted parchment alert used throughout the app for form/page errors.
// Render nothing when `message` is falsy so callers can pass state unconditionally.
// Pass `onRetry` to render a "Try again" button inside the alert.
export default function ErrorAlert({ message, onRetry, className = '' }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className={`text-ember-deep text-body bg-ember/10 px-3 py-2 rounded-lg border border-ember/40 font-body ${onRetry ? 'flex items-center gap-3' : ''} ${className}`}
    >
      <span className={onRetry ? 'flex-1' : ''}>{message}</span>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="shrink-0">
          Try again
        </Button>
      )}
    </div>
  );
}
