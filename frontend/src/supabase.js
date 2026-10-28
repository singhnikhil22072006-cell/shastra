import { createClient } from "@supabase/supabase-js";

// Anon key only. The service-role key must never reach the browser.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);
