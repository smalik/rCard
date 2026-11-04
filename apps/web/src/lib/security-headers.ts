// Headers sent with every page and asset. Plytos has no public pages in v1,
// so nothing may be indexed, framed, or leak a referrer.

export type Header = { key: string; value: string };

export function contentSecurityPolicy({ dev }: { dev: boolean }): string {
  // Next.js inlines small scripts, so script-src needs 'unsafe-inline' until
  // nonce-based CSP lands. Dev mode also needs 'unsafe-eval' for fast refresh.
  const scriptSrc = ["'self'", "'unsafe-inline'", ...(dev ? ["'unsafe-eval'"] : [])];
  return [
    "default-src 'self'",
    `script-src ${scriptSrc.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

// The person's own resume file, opened in the browser. It runs no scripts of
// Plytos's; the browser's PDF viewer needs object-src to show a PDF inline.
export function fileContentSecurityPolicy(): string {
  return [
    "default-src 'none'",
    "object-src 'self'",
    "img-src 'self' data: blob:",
    "style-src 'unsafe-inline'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function securityHeaders({ dev }: { dev: boolean }): Header[] {
  return [
    { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive, nosnippet, noimageindex" },
    { key: "Referrer-Policy", value: "no-referrer" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    // Camera and microphone stay available to Plytos itself for photo and
    // voice notes; nothing else gets them.
    { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
    { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
    { key: "Content-Security-Policy", value: contentSecurityPolicy({ dev }) },
  ];
}
