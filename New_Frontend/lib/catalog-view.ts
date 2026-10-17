import type { Category, PageResult, Product } from './api';

export type CatalogFilter = {
  category: string; search: string; sort: string; platform: string;
  offer: string; currency: string; min_price: string; max_price: string; page: number;
};
export type CatalogFacet = { value: string; label: string; count: number };
export type CatalogResult = PageResult<Product> & {
  total_count?: number;
  facets?: { platforms: CatalogFacet[]; currencies: CatalogFacet[]; offers: CatalogFacet[] };
};
export const emptyCatalogFilter: CatalogFilter = {
  category: '', search: '', sort: 'newest', platform: '', offer: '', currency: '', min_price: '', max_price: '', page: 1,
};
export function categoryValue(category: Category) { return typeof category === 'string' ? category : category.value || category.slug || category.name || ''; }
export function categoryLabel(category: Category) { return typeof category === 'string' ? category : category.label || category.name || categoryValue(category); }
export function catalogFilterFromQuery(query: URLSearchParams, initialCategory = ''): CatalogFilter {
  const filter = { ...emptyCatalogFilter, category: query.has('category') ? query.get('category') || '' : initialCategory };
  for (const key of ['search', 'platform', 'offer', 'currency', 'min_price', 'max_price'] as const) filter[key] = query.get(key) || '';
  filter.sort = ['newest', 'oldest', 'price_asc', 'price_desc'].includes(query.get('sort') || '') ? query.get('sort')! : 'newest';
  const page = Number(query.get('page'));
  filter.page = Number.isSafeInteger(page) && page > 0 ? page : 1;
  // A price comparison across currencies would be misleading.
  if (!filter.currency) { filter.min_price = ''; filter.max_price = ''; if (filter.sort.startsWith('price_')) filter.sort = 'newest'; }
  return filter;
}
export function catalogQuery(filter: CatalogFilter, initialCategory = ''): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) {
    if (value !== '' && !(key === 'page' && value === 1) && !(key === 'sort' && value === 'newest')) query.set(key, String(value));
  }
  // A category route needs an explicit empty value so reload/back does not
  // silently restore its initial category after the member selects All.
  if (initialCategory && !filter.category) query.set('category', '');
  return query.toString();
}
export function priceRangeError(min: string, max: string): string {
  if ([min, max].some(value => value !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0))) return 'Enter a valid, non-negative price.';
  if ([min, max].some(value => Number(value) > 999999999999)) return 'Enter a price below 1 trillion.';
  if (min !== '' && max !== '' && Number(min) > Number(max)) return 'The minimum price must be lower than the maximum.';
  return '';
}
export function filterCount(filter: CatalogFilter): number {
  return [filter.category, filter.search, filter.platform, filter.offer, filter.currency, filter.min_price || filter.max_price].filter(Boolean).length;
}
export function productImages(product: Product): string[] {
  const images = [product.main_image || product.thumbnail, ...(product.images || []).map(image => typeof image === 'string' ? image : image.image || image.url || '')];
  return [...new Set(images.filter(Boolean))];
}
export function platformLabel(value: string): string {
  return ({ amazon: 'Amazon', ebay: 'eBay', aliexpress: 'AliExpress', other: 'Partner store', none: 'Direct' } as Record<string, string>)[value] || 'Partner store';
}
