import { NextRequest, NextResponse } from "next/server";
import { ADMIN_COOKIE, checkPassword, isUnlocked } from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

/** Whether this browser is currently unlocked — drives the lock/unlock control in the UI. */
export async function GET(request: NextRequest) {
  return NextResponse.json({
    unlocked: isUnlocked(request),
    configured: Boolean(process.env.ADMIN_PASSWORD),
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const token = checkPassword(body?.password);

  if (!token) {
    return NextResponse.json({ error: "Wrong password." }, { status: 401 });
  }

  const response = NextResponse.json({ unlocked: true });
  response.cookies.set(ADMIN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ unlocked: false });
  response.cookies.delete(ADMIN_COOKIE);
  return response;
}
