import assert from 'node:assert/strict';
import test from 'node:test';
import {
  catalogFilterFromQuery, catalogQuery, categoryLabel, categoryValue,
  emptyCatalogFilter, filterCount, platformLabel, priceRangeError, productImages,
} from '../lib/catalog-view.ts';

test('catalog URLs preserve searchable text, filters and pagination on reload', () => {
  const filter = {
    ...emptyCatalogFilter, category: 'merges_1_0', search: 'Optimus & Bee / #1',
    platform: 'amazon', offer: 'sale', currency: 'USD', min_price: '12.50',
    max_price: '80', sort: 'price_asc', page: 3,
  };
  const query = catalogQuery(filter);
  assert.deepEqual(catalogFilterFromQuery(new URLSearchParams(query)), filter);
  assert.equal(new URLSearchParams(query).get('search'), 'Optimus & Bee / #1');
  assert.equal(catalogQuery(emptyCatalogFilter), '');
});

test('All products remains selected after reloading a category route or revisiting its URL', () => {
  const categoryRoute = 'transformers_2_0';
  assert.equal(catalogFilterFromQuery(new URLSearchParams(), categoryRoute).category, categoryRoute);
  const clearedUrl = catalogQuery({ ...emptyCatalogFilter }, categoryRoute);
  assert.equal(new URLSearchParams(clearedUrl).has('category'), true);
  assert.equal(catalogFilterFromQuery(new URLSearchParams(clearedUrl), categoryRoute).category, '');
  const otherCategoryUrl = catalogQuery({ ...emptyCatalogFilter, category: 'merges_1_0' }, categoryRoute);
  assert.equal(catalogFilterFromQuery(new URLSearchParams(otherCategoryUrl), categoryRoute).category, 'merges_1_0');
});

test('price sorting and bounds never compare mixed currencies from a pasted URL', () => {
  const filter = catalogFilterFromQuery(new URLSearchParams('sort=price_desc&min_price=1&max_price=100&platform=amazon'));
  assert.equal(filter.currency, '');
  assert.equal(filter.sort, 'newest');
  assert.equal(filter.min_price, '');
  assert.equal(filter.max_price, '');
  assert.equal(filter.platform, 'amazon');
  const valid = catalogFilterFromQuery(new URLSearchParams('sort=price_desc&currency=KWD&min_price=1.001&max_price=1.999'));
  assert.equal(valid.sort, 'price_desc');
  assert.equal(valid.min_price, '1.001');
  assert.equal(valid.max_price, '1.999');
  assert.deepEqual(catalogFilterFromQuery(new URLSearchParams(catalogQuery(valid))), valid);
});

test('invalid sorting and pagination safely return to the first newest page', () => {
  for (const value of ['0', '-1', '1.5', 'Infinity', 'NaN', '9007199254740992']) {
    const filter = catalogFilterFromQuery(new URLSearchParams({ page: value, sort: 'bestselling' }));
    assert.equal(filter.page, 1);
    assert.equal(filter.sort, 'newest');
  }
  assert.equal(catalogFilterFromQuery(new URLSearchParams('page=2&sort=oldest')).page, 2);
});

test('price ranges accept zero and three-decimal amounts without rounding', () => {
  for (const [min, max] of [['', ''], ['0', '0'], ['1.001', '1.009'], ['', '1.001'], ['1.001', ''], ['999999999999', '999999999999']]) {
    assert.equal(priceRangeError(min, max), '');
  }
  for (const [min, max] of [['-0.01', ''], ['', '-1'], ['Infinity', ''], ['NaN', ''], ['oops', '1'], ['1.01', '1.001'], ['1000000000000', '']]) {
    assert.notEqual(priceRangeError(min, max), '', `${min} to ${max} must be rejected`);
  }
});

test('filter count groups two price bounds as one active range and excludes sorting', () => {
  assert.equal(filterCount({ ...emptyCatalogFilter, sort: 'oldest', page: 2 }), 0);
  assert.equal(filterCount({ ...emptyCatalogFilter, currency: 'USD', min_price: '10', max_price: '20' }), 2);
  assert.equal(filterCount({ ...emptyCatalogFilter, search: 'Bee', category: 'merges_1_0', platform: 'amazon', offer: 'sale' }), 4);
});

test('gallery images retain their real order while removing duplicates and missing slots', () => {
  assert.deepEqual(productImages({ main_image: '/hero.jpg', thumbnail: '/thumb.jpg', images: ['/hero.jpg', '', { image: '/side.jpg' }, { url: '/rear.jpg' }, {}, '/side.jpg'] }), ['/hero.jpg', '/side.jpg', '/rear.jpg']);
  assert.deepEqual(productImages({ main_image: '', thumbnail: '/thumb.jpg', images: [{ url: '/rear.jpg' }] }), ['/thumb.jpg', '/rear.jpg']);
  assert.deepEqual(productImages({ main_image: '', thumbnail: '', images: [] }), []);
});

test('labels preserve backend category labels and identify supported store types', () => {
  assert.equal(categoryValue({ value: 'merges_1_0', label: 'Merges & Figures' }), 'merges_1_0');
  assert.equal(categoryLabel({ value: 'merges_1_0', label: 'Merges & Figures' }), 'Merges & Figures');
  assert.equal(categoryValue('Legacy category'), 'Legacy category');
  assert.equal(categoryLabel('Legacy category'), 'Legacy category');
  assert.equal(platformLabel('none'), 'Direct');
  assert.equal(platformLabel('amazon'), 'Amazon');
  assert.equal(platformLabel('other'), 'Partner store');
});
