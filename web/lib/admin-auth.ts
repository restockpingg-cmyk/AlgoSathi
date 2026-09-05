import "server-only";
import { createHmac, timingSafeEqual } from "crypto";
import { NextRequest, NextResponse } from "next/server";

/** Shared-password gate for the routes that can change what the bot trades.
 *
 * Reads stay public — anyone with the link can view trades and run backtests. Writes
 * (creating, editing, and above all *activating* a strategy) need the password, because an
 * active strategy is what the live bot picks up once strategy.source is set to supabase.
 *
 * This is deliberately a single shared password rather than real accounts: it exists to stop
 * a public URL from being a control panel for someone else's money, not to tell friends
 * apart. Per-user accounts are a separate, larger change.
 */

export const ADMIN_COOKIE = "algosathi_admin";

/** The cookie stores an HMAC of the password rather than the password itself, so a leaked
 * cookie can't be read back off the wire as the plaintext to type in elsewhere. */
function tokenFor(password: string): string {
  return createHmac("sha256", password).update("algosathi-admin-v1").digest("hex");
}

function equals(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  // timingSafeEqual throws on length mismatch, so check that first — the length of a hex
  // digest is not a secret.
  return left.length === right.length && timingSafeEqual(left, right);
}

export function expectedToken(): string | null {
  const password = process.env.ADMIN_PASSWORD;
  return password ? tokenFor(password) : null;
}

export function checkPassword(password: unknown): string | null {
  const expected = process.env.ADMIN_PASSWORD;
  if (!expected || typeof password !== "string") return null;
  return equals(tokenFor(password), tokenFor(expected)) ? tokenFor(expected) : null;
}

export function isUnlocked(request: NextRequest): boolean {
  const expected = expectedToken();
  if (!expected) return false;
  const cookie = request.cookies.get(ADMIN_COOKIE)?.value;
  return typeof cookie === "string" && equals(cookie, expected);
}

/** Returns a 401 response to return early, or null when the caller may proceed. */
export function requireAdmin(request: NextRequest): NextResponse | null {
  if (!process.env.ADMIN_PASSWORD) {
    // Fail closed. A missing password must lock the app down rather than leave the
    // strategy-activation endpoints open to anyone who has the URL.
    return NextResponse.json(
      { error: "Writes are disabled: ADMIN_PASSWORD is not set on the server." },
      { status: 401 }
    );
  }
  if (!isUnlocked(request)) {
    return NextResponse.json(
      { error: "Locked. Enter the admin password to save or activate strategies." },
      { status: 401 }
    );
  }
  return null;
}
