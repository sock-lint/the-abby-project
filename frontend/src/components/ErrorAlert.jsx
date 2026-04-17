// Ember-tinted parchment alert used throughout the app for form/page errors.
// Render nothing when `message` is falsy so callers can pass state unconditionally.
export default function ErrorAlert({ message, className = '' }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className={`text-ember-deep text-sm bg-ember/10 px-3 py-2 rounded-lg border border-ember/40 font-body ${className}`}
    >
      {message}
    </div>
  );
}
