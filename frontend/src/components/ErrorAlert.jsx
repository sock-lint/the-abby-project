// Thin red-alert strip used throughout the app for form/page error messages.
// Render nothing when `message` is falsy so callers can pass state unconditionally.
export default function ErrorAlert({ message, className = '' }) {
  if (!message) return null;
  return (
    <div
      className={`text-red-400 text-sm bg-red-400/10 px-3 py-2 rounded-lg border border-red-400/30 ${className}`}
    >
      {message}
    </div>
  );
}
