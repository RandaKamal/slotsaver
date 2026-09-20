/**
 * Where the browser sends its API requests.
 *
 * NEXT_PUBLIC_* values are inlined at BUILD time, not read at runtime, so this
 * cannot be corrected with an env var after the image is built. It does not
 * need to be: the deployed app serves the frontend and the API from a single
 * origin (/ -> web, /api -> api), so an empty base makes every call a
 * same-origin relative request that is correct by construction and survives
 * the app's URL changing. Only local dev genuinely needs an absolute
 * cross-origin URL. Setting NEXT_PUBLIC_API_URL explicitly still wins in both.
 */
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");
