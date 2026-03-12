import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Comma-separated list of emails allowed to access the dashboard.
// Set ALLOWED_EMAILS in Vercel env. Defaults to the owner.
const ALLOWED: string[] = (
  process.env.ALLOWED_EMAILS ?? "info@genesis-analytics.io"
)
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

function isAllowed(email: string | undefined | null): boolean {
  return ALLOWED.includes((email ?? "").toLowerCase());
}

export async function proxy(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;

  // ── /dashboard — must be authenticated AND on the allowlist ──────────────
  if (pathname.startsWith("/dashboard")) {
    if (!user || !isAllowed(user.email)) {
      return NextResponse.redirect(new URL("/waitlist", request.url));
    }
  }

  // ── /login — skip form for already-authorized users; block others ─────────
  if (pathname === "/login") {
    if (user && isAllowed(user.email)) {
      const dest =
        process.env.NEXT_PUBLIC_DASHBOARD_URL ||
        "http://localhost:8000/dashboard/";
      return NextResponse.redirect(dest);
    }
    if (user && !isAllowed(user.email)) {
      // Authenticated but not authorized — send to waitlist
      return NextResponse.redirect(new URL("/waitlist", request.url));
    }
    // Unauthenticated — show the login form (owner needs this to sign in)
  }

  return supabaseResponse;
}

export const config = {
  matcher: ["/dashboard/:path*", "/login"],
};
