/**
 * POST /api/v1/auth/register — Register a new account (self-service vendor registration).
 *
 * Creates a User with the specified role. If the role is `VENDOR`, also creates
 * a VendorProfile in `PENDING_APPROVAL` status, requiring admin approval before
 * the vendor can list products. When no password is provided for VENDOR role,
 * a cryptographically random 16-character password is generated server-side.
 *
 * ## Request Body
 * ```json
 * {
 *   "email": "vendor@example.com",       // Required: string, valid email format
 *   "password": "SecurePass123!",         // Optional for VENDOR (auto-generated); required otherwise
 *   "role": "VENDOR",                     // Optional: 'ADMIN' | 'VENDOR' | 'CUSTOMER' | 'SUPPORT'. Defaults to 'CUSTOMER'.
 *   "businessName": "My Store LLC",       // Optional: string, used when role is VENDOR
 *   "taxId": "12-3456789",                // Optional: string, used when role is VENDOR
 *   "address": {                          // Optional: AddressInput object (used when role is VENDOR)
 *     "street": "123 Main St",
 *     "city": "Springfield",
 *     "state": "IL",
 *     "postalCode": "62701",
 *     "country": "US"
 *   },
 *   "description": "A quality electronics store"  // Optional: string, vendor description
 * }
 * ```
 *
 * ## Response Codes
 * | Status | Meaning | Body |
 * |--------|---------|------|
 * | `201` | Account created successfully | `{ message: "Registration submitted for approval" }` |
 * | `400` | Validation failure — missing or invalid fields | `{ error: string, field?: string }` (field identifies which input failed) |
 * | `409` | Email already registered | `{ error: "Email already registered" }` |
 * | `500` | Internal server error | `{ error: "Internal server error" }` |
 *
 * ## Validation Rules
 * - **email**: Required, must be a non-empty string. Stored in lowercase. Duplicate emails return 409.
 * - **password**: Required unless role is VENDOR (auto-generated). Minimum 8 characters when provided explicitly.
 * - **role**: Must be one of `ADMIN`, `VENDOR`, `CUSTOMER`, or `SUPPORT`. Defaults to `CUSTOMER` if omitted.
 * - **businessName**, **taxId**, **address**, **description**: Optional; used for VENDOR role registrations.
 *
 * ## Security Assumptions
 * - Passwords are hashed with bcrypt at cost factor 12 (SR-7) before storage.
 * - Email comparison is case-insensitive: "Vendor@Example.com" and "vendor@example.com" are treated as duplicates.
 * - No rate limiting is implemented in this endpoint (deferred to a later sprint).
 * - The endpoint does not require authentication — it is the entry point for new account creation.
 *
 * ## Error Catalogue
 * - **ERR-019** (Validation failure): Returned when required fields are missing or invalid. Includes `field` property identifying the failed input.
 * - Duplicate email conflict: Returns 409 with message "Email already registered".
 *
 * @module POST /api/v1/auth/register
 */

import { NextResponse } from 'next/server';
import prisma from '@/lib/prisma/client';
import bcrypt from 'bcryptjs';

const COST_FACTOR = 12;

/** Generate a cryptographically random alphanumeric string of given length. */
function generateRandomString(length: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars[bytes[i] % chars.length];
  }
  return result;
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { email, password, role, businessName, taxId, address, description } = body as {
      email?: string; password?: string; role?: string;
      businessName?: string; taxId?: string; address?: Record<string, string>; description?: string;
    };

    // Validate required fields
    if (!email) {
      return NextResponse.json({ error: 'Email is required', field: 'email' }, { status: 400 });
    }

    const lowerEmail = email.toLowerCase().trim();

    // Check for duplicate email
    const existingUser = await prisma.user.findUnique({ where: { email: lowerEmail } });
    if (existingUser) {
      return NextResponse.json({ error: 'Email already registered' }, { status: 409 });
    }

    // Determine role — default to CUSTOMER
    const userRole = role || 'CUSTOMER';
    const validRoles = ['ADMIN', 'VENDOR', 'CUSTOMER', 'SUPPORT'];
    if (!validRoles.includes(userRole)) {
      return NextResponse.json({ error: 'Invalid role specified' }, { status: 400 });
    }

    // Password handling — required unless VENDOR (UI flow generates one)
    let finalPassword = password;
    if (!finalPassword) {
      if (userRole === 'VENDOR') {
        // Generate a secure random password for vendor registration via UI form
        finalPassword = generateRandomString(16);
      } else {
        return NextResponse.json({ error: 'Password is required', field: 'password' }, { status: 400 });
      }
    }

    // Validate password length (only if explicitly provided)
    if (password && password.length < 8) {
      return NextResponse.json({ error: 'Password must be at least 8 characters', field: 'password' }, { status: 400 });
    }

    // Hash password
    const passwordHash = await bcrypt.hash(finalPassword, COST_FACTOR);

    // Create user
    const user = await prisma.user.create({
      data: {
        email: lowerEmail,
        passwordHash,
        role: userRole,
        twoFactorEnabled: false,
      },
    });

    // If vendor role, create VendorProfile in PENDING_APPROVAL status
    if (userRole === 'VENDOR') {
      await prisma.vendorProfile.create({
        data: {
          userId: user.id,
          businessName: businessName || '',
          taxId: taxId || `TAX-${Date.now()}`, // auto-generate if not provided
          status: 'PENDING_APPROVAL',
          description: description || '',
        },
      });
    }

    return NextResponse.json(
      { message: 'Registration submitted for approval' },
      { status: 201 },
    );
  } catch (err) {
    console.error('Registration error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
