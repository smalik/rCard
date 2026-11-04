import type { IconDefinition } from "@fortawesome/free-solid-svg-icons";

// Draws a Font Awesome icon as inline SVG. Only the path data ships, so
// there's no icon font, no injected stylesheet, and it renders on the server.
export function Icon({
  icon,
  size = 14,
  className,
  label,
}: {
  icon: IconDefinition;
  size?: number;
  className?: string;
  // Icons are decorative unless they carry meaning on their own.
  label?: string;
}) {
  const [width, height, , , path] = icon.icon;
  const paths = Array.isArray(path) ? path : [path];
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      viewBox={`0 0 ${width} ${height}`}
      height={size}
      width={(size * width) / height}
      fill="currentColor"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}
