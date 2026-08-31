import "server-only";
import { createClient } from "@supabase/supabase-js";

/** Service-role Supabase client for API routes only — never import this from a "use
 * client" file or expose SUPABASE_SERVICE_ROLE_KEY to the browser. */
export function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY env vars");
  }
  return createClient(url, key);
}
