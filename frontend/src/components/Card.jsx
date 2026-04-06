export default function Card({ children, className = '', ...props }) {
  return (
    <div
      className={`bg-forge-card border border-forge-border rounded-xl p-4 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
