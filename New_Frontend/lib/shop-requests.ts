import type { CatalogFilter } from './catalog-view';

export type FeaturedRequest = {
  id: number; title: string; description: string; details: string; image: string | null;
  icon: 'edit' | 'media'; badge: string; price_label: string; turnaround: string;
  button_label: string; placeholder_label: string; is_placeholder: boolean; purchase_url: string;
};

/** Requests are pinned on the first catalog page, without bypassing product filters. */
export function pinnedRequests(items: FeaturedRequest[], filter: CatalogFilter): FeaturedRequest[] {
  if (filter.page !== 1 || filter.category || filter.platform || filter.offer || filter.currency || filter.min_price || filter.max_price) return [];
  const search = filter.search.trim().toLocaleLowerCase();
  return items.filter(item => !search || `${item.title} ${item.description}`.toLocaleLowerCase().includes(search));
}
