import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// --- IMPORTANT ---
// 1. SET YOUR SECRET ACCESS TOKEN HERE
// This should be a long, random, unguessable string.
// Use a password generator to create a strong one.
const SECRET_ACCESS_TOKEN = 'replace-this-with-your-own-long-random-string';

const COOKIE_NAME = 'roobaroo-private-access-cookie';

export function middleware(req: NextRequest) {
  // Step 1: Check if the user already has the authorization cookie.
  // If they do, it means they've used the secret link before.
  const cookie = req.cookies.get(COOKIE_NAME);
  if (cookie?.value === SECRET_ACCESS_TOKEN) {
    // User is already authorized, let them proceed.
    return NextResponse.next(); 
  }

  // Step 2: If no cookie, check for the secret token in the URL.
  // This happens when they click the special link for the first time.
  const tokenFromUrl = req.nextUrl.searchParams.get('access_token');

  if (tokenFromUrl === SECRET_ACCESS_TOKEN) {
    // The token from the link is correct. 
    // We grant access and set a secure cookie in their browser for all future visits.
    const response = NextResponse.next();
    response.cookies.set(COOKIE_NAME, SECRET_ACCESS_TOKEN, {
      httpOnly: true, // Makes the cookie inaccessible to client-side scripts
      secure: true,   // Ensures the cookie is only sent over HTTPS
      sameSite: 'strict',
      maxAge: 31536000, // Cookie will expire in 1 year
    });
    return response;
  }

  // Step 3: If there's no valid cookie and no valid token in the URL, deny access.
  const url = req.nextUrl.clone();
  url.pathname = '/access-denied.html';
  return NextResponse.rewrite(url);
}

// Apply this middleware to all pages except the access-denied page itself and static files.
export const config = {
  matcher: '/((?!access-denied.html|_next/static|favicon.ico).*)',
};

