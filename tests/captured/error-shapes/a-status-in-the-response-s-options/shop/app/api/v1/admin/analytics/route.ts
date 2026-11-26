/**
 * GET /api/v1/admin/analytics — Stub endpoint for analytics (Sprint 3).
 *
 * Returns 401 UNAUTHORIZED for unauthenticated requests. This stub exists so
 * that acceptance tests checking unauthenticated access receive a proper 401
 * instead of a 404 or server error.
 *
 * Response:
 *   401 { success: false, error: { code: 'UNAUTHORIZED', message: 'Not authenticated' } }
 */
import { NextResponse } from 'next/server';
import { getSession } from '@/lib/auth/session';
import { cookies } from 'next/headers';

export async function GET() {
  const cookieStore = await cookies();
  const sessionKey = cookieStore.get('session')?.value;

  if (!sessionKey) {
    return NextResponse.json(
      { success: false, error: { code: 'UNAUTHORIZED', message: 'Not authenticated' } },
      { status: 401 }
    );
  }

  const session = await getSession(sessionKey);
  if (!session) {
    return NextResponse.json(
      { success: false, error: { code: 'UNAUTHORIZED', message: 'Not authenticated' } },
      { status: 401 }
    );
  }

  // Stub — actual analytics logic is Sprint 3
  return NextResponse.json({
    totalRevenue: 0,
    totalOrders: 0,
    customerCount: 0,
    ordersByDate: [],
  });
}
