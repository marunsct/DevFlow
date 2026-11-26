/**
 * Shopping cart items API routes (Sprint 2).
 *
 * POST   /api/v1/cart/items — Add an item to the authenticated user's cart.
 *         Body: { productId: string, quantity: number }
 *
 * Every protected endpoint calls extractAuthFromRequest from lib/auth.ts to get the
 * authenticated user's { userId, role }. Returns 401 if no token is present.
 */

import { NextResponse } from 'next/server';
import { extractAuthFromRequest } from '@/lib/auth';
import { addToCart } from '@/lib/cart';

// ---------------------------------------------------------------------------
// POST /api/v1/cart/items — Add an item to the user's shopping cart.
// ---------------------------------------------------------------------------

/**
 * Add a product to the authenticated user's shopping cart, or increment its
 * quantity if it is already present. Stock availability is validated before any
 * mutation.
 *
 * **Body** — { productId: string, quantity: number }
 * - `productId` must reference an existing product.
 * - `quantity` must be > 0 and the total (existing + new) cannot exceed stock.
 *
 * **Response**
 * - 200 { message: 'Item added', item: CartItemResponse } on success.
 * - 400 { error: string } for validation failures (quantity ≤ 0, not enough stock).
 * - 401 { error: 'Not authenticated' } if no valid token.
 * - 404 { error: 'Product not found or out of stock' } if the product does not exist
 *   or has insufficient inventory.
 */
export async function POST(request: Request) {
  // Authenticate the caller via JWT in Authorization header or cookie.
  const auth = extractAuthFromRequest(request);
  if (!auth) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

    // Parse and validate required fields. `body` is `unknown`; cast to a record after JSON parse.
    const parsedBody = body as Record<string, unknown>;
    const productId = typeof parsedBody?.productId === 'string' ? (parsedBody.productId as string) : undefined;
    const quantity = typeof parsedBody?.quantity === 'number' ? (parsedBody.quantity as number) : undefined;

  if (!productId) {
    return NextResponse.json(
      { error: 'Missing required field: productId' },
      { status: 400 },
    );
  }

  if (quantity == null || quantity <= 0) {
    return NextResponse.json(
      { error: 'Quantity must be greater than zero' },
      { status: 400 },
    );
  }

  try {
    const item = await addToCart(auth.userId, productId, quantity);

    return NextResponse.json(
      { message: 'Item added', item },
      { status: 200 },
    );
  } catch (err: any) {
    // Map service-layer errors to HTTP responses.
    if (err.message === 'Product not found') {
      return NextResponse.json(
        { error: 'Product not found or out of stock' },
        { status: 404 },
      );
    }

    if (err.message === 'Not enough stock') {
      return NextResponse.json(
        { error: 'Not enough stock' },
        { status: 400 },
      );
    }

    console.error('Error adding item to cart:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
