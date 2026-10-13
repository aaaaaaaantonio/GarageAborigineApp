type QueryValue = string | number | boolean | null | undefined | readonly string[];

/** `?a=1&s=x&s=y`: arrays repeat the key; null, undefined, false and empty arrays are left out. */
export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === false) continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}
