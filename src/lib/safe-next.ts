/**
 * Only same-site relative paths may be used as a post-login destination.
 * Rejects "//host", "/\host", encoded variants, control characters and anything not starting with a single "/".
 */
export function safeNext(value: unknown, fallback = "/me"): string {
  if (typeof value !== "string" || value.length > 300) return fallback;
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return fallback;
  }
  if (!/^\/(?![/\\])[^\s\\\u0000-\u001f]*$/.test(decoded) || !/^\/(?![/\\])[^\s\\\u0000-\u001f]*$/.test(value)) return fallback;
  return value;
}
