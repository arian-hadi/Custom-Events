import assert from 'node:assert/strict';
import test from 'node:test';
import { currencyLabel, stripeCheckoutUrl, paymentStatusLabel } from '../lib/commerce.ts';
import { amazonFreshness, nextAmazonExpiry } from '../lib/amazon-freshness.ts';

test('payment redirect only permits the exact hosted Stripe origin', () => {
  assert.equal(stripeCheckoutUrl('https://checkout.stripe.com/c/pay/cs_test_123'), 'https://checkout.stripe.com/c/pay/cs_test_123');
  for (const value of ['https://checkout.stripe.com.evil.test/c/pay', 'https://checkout.stripe.com@evil.test', 'https://evil.test', 'http://checkout.stripe.com', 'javascript:alert(1)', '//checkout.stripe.com', 'https://user@checkout.stripe.com/pay', 'https://checkout.stripe.com:444/pay']) assert.equal(stripeCheckoutUrl(value), null);
});
test('missing or malformed prices never become a free product', () => {
  for (const value of [null, undefined, '', 'NaN', 'Infinity']) assert.equal(currencyLabel(value), 'Price unavailable');
  assert.equal(currencyLabel('0', 'USD'), '$0.00');
  assert.equal(currencyLabel('123', 'JPY'), '¥123');
});
test('only confirmed paid server state is described as paid', () => {
  assert.equal(paymentStatusLabel('paid'), 'Payment confirmed');
  assert.equal(paymentStatusLabel('success'), 'Payment confirmation pending');
});

test('Amazon offers and content expire in open tabs using server time, including the exact boundary', () => {
  const product = { amazon_automated: true, amazon_observed_at: '2026-01-01T00:00:00Z', amazon_offer_expires_at: '2026-01-01T00:00:05Z', amazon_content_expires_at: '2026-01-01T00:00:10Z' };
  assert.deepEqual(amazonFreshness(product, 4999), { contentFresh: true, offerFresh: true });
  assert.deepEqual(amazonFreshness(product, 5000), { contentFresh: true, offerFresh: false });
  assert.deepEqual(amazonFreshness(product, 10000), { contentFresh: false, offerFresh: false });
  assert.equal(nextAmazonExpiry(product, 5000), 5000);
  assert.equal(nextAmazonExpiry(product, 10000), null);
  assert.deepEqual(amazonFreshness({ ...product, amazon_offer_expires_at: null }, 0), { contentFresh: true, offerFresh: false });
  assert.deepEqual(amazonFreshness({ ...product, amazon_observed_at: undefined }, 0), { contentFresh: false, offerFresh: false });
  assert.deepEqual(amazonFreshness({}, 999999999), { contentFresh: true, offerFresh: true });
});
