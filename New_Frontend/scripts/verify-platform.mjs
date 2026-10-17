import assert from 'node:assert/strict';

// Read-only integration smoke checks. Run with the local Django backend and
// Next frontend/gateway running; no users or database fixtures are created.
const base = (process.env.FRONTEND_URL || 'http://localhost:5173').replace(/\/$/, '');
const routes = ['/', '/store', '/blog', '/news', '/contact-us', '/editing-hub', '/events', '/applications', '/account', '/account/profile', '/account/settings', '/account/orders', '/account/preferences', '/favorites', '/notifications', '/login', '/register', '/verify-email', '/forgot-password', '/reset-password', '/community-updates'];
const assetUrls = new Set();
for (const route of routes) {
  const response = await fetch(`${base}${route}`, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200, `${route} should render`);
  const html = await response.text();
  assert.match(html, /main-content/, `${route} must use the shared site layout`);
  assert.doesNotMatch(html, /<script[^>]+src=["'][^"']*(?:replica\.js|jquery|webflow)/i, `${route} must not load fake cart/form handlers`);
  for (const [, asset] of html.matchAll(/(?:src|href)="(\/assets\/[^"?#]+)"/g)) assetUrls.add(asset);
  console.log(`OK page ${route}`);
}
const missing = await fetch(`${base}/this-page-does-not-exist`, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
assert.equal(missing.status, 404, 'Unknown page must return 404');
for (const asset of assetUrls) {
  const response = await fetch(`${base}${asset}`, { method: 'HEAD', redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200, `Missing asset ${asset}`);
}
for (const endpoint of ['site/', 'products/', 'blog/', 'events/', 'announcements/', 'contact/', 'auth/session/', 'league/status/', 'league/rounds/', 'league/standings/?period=season', 'league/winners/']) {
  const response = await fetch(`${base}/api/v2/${endpoint}`, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200, `Django API ${endpoint} should be reachable through the frontend origin`);
  assert.match(response.headers.get('content-type') || '', /application\/json/, `${endpoint} must return JSON`);
  const data = await response.json();
  if (endpoint === 'site/') assert.ok(data.site?.name, 'Site settings must be available');
  if (endpoint === 'auth/session/') { assert.equal(data.user, null); assert.ok(data.csrf_token, 'Anonymous sessions require a CSRF token'); }
  if (['products/', 'blog/', 'events/', 'announcements/'].includes(endpoint)) assert.ok(Array.isArray(data.results), `${endpoint} needs a result list`);
  if (endpoint === 'products/') {
    assert.ok(Array.isArray(data.facets?.currencies), 'Catalog currency facets must be available');
    assert.ok(Array.isArray(data.facets?.platforms), 'Catalog store facets must be available');
  }
  if (endpoint === 'league/rounds/') assert.ok(Array.isArray(data.rounds) && Array.isArray(data.seasons), 'League history must provide round and season metadata');
  if (endpoint.startsWith('league/standings/')) assert.ok(Array.isArray(data.rows), 'League standings must provide rows');
  console.log(`OK API ${endpoint}`);
}
for (const endpoint of ['member/dashboard/', 'auth/profile/', 'favorites/', 'applications/', 'notifications/', 'notification-preferences/']) {
  const response = await fetch(`${base}/api/v2/${endpoint}`, { redirect: 'manual', signal: AbortSignal.timeout(15000) });
  assert.ok([401, 403].includes(response.status), `${endpoint} must require authentication`);
}
const noCsrf = await fetch(`${base}/api/v2/auth/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'nobody@example.invalid', password: 'unused' }), redirect: 'manual', signal: AbortSignal.timeout(15000) });
assert.equal(noCsrf.status, 403, 'Login mutations must require CSRF');
console.log(`Verified ${routes.length} pages, ${assetUrls.size} assets, public APIs, private access and CSRF at ${base}.`);


