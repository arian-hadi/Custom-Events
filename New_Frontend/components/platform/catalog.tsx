'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ArrowDownUp, ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, Heart, ImageOff, Search, ShieldCheck, SlidersHorizontal, X } from 'lucide-react';
import { dateLabel, mutate, safeUrl, useResource, type Category, type PageResult, type Post, type Product } from '@/lib/api';
import { useSite } from './site-shell';
import { AccountNav } from './account-nav';
import { Empty, ErrorNotice, Loading, Notice, PageHeading, Pagination, RichText } from './ui';
import { currencyLabel } from '@/lib/commerce';
import { CheckoutButton } from './payments';
import { FeaturedShopRequests } from './featured-shop-requests';
import { useAmazonProduct } from '@/lib/use-amazon-product';
import { catalogFilterFromQuery, catalogQuery, categoryLabel, categoryValue, emptyCatalogFilter, filterCount, platformLabel, priceRangeError, productImages, type CatalogFilter, type CatalogResult } from '@/lib/catalog-view';

function plainText(html?: string) { return (html || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').trim(); }
function Price({ product }: { product: Product }) {
  if (product.checkout?.configured) return <span className="v2-price">{currencyLabel(product.checkout.display_amount, product.checkout.currency)}</span>;
  if (product.price_available === false || product.current_price === null) return <span className="v2-price">Check price on Amazon</span>;
  return <span className="v2-price">{product.is_free ? 'Free' : currencyLabel(product.current_price, product.currency)}{!product.is_free && product.original_price !== null && Number(product.original_price) > Number(product.current_price) && <del>{currencyLabel(product.original_price, product.currency)}</del>}</span>;
}
function AmazonNotices({ product, compact = false }: { product: Product; compact?: boolean }) {
  if (!product.amazon_automated) return null;
  const details = <>{product.price_disclaimer && <p>{product.price_disclaimer}</p>}{product.content_disclosure && <p>{product.content_disclosure}</p>}</>;
  return <div className="v2-small v2-muted"><p>{product.affiliate_disclosure}</p>{product.price_updated_at && <p>Price checked {new Date(product.price_updated_at).toLocaleString('en', { timeZone: 'UTC', timeZoneName: 'short' })}.</p>}{compact ? <details><summary>Amazon price and content information</summary>{details}</details> : details}</div>;
}
function CatalogImage({ src, alt, className = '', priority = false }: { src: string; alt: string; className?: string; priority?: boolean }) {
  const [failed, setFailed] = useState('');
  return src && failed !== src ? <img src={src} alt={alt} className={className} loading={priority ? 'eager' : 'lazy'} onError={() => setFailed(src)} /> : <span className={`v2-shop-image-fallback ${className}`}><ImageOff size={30} aria-hidden="true" /><span>Image unavailable</span></span>;
}
function FavoriteButton({ product, expanded = false, onRemoved }: { product: Product; expanded?: boolean; onRemoved?: () => void }) {
  const { user } = useSite();
  const [favorite, setFavorite] = useState(product.is_favorite);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => { setFavorite(product.is_favorite); }, [product.id, product.is_favorite]);
  async function toggle() {
    if (!user) { window.location.assign(`/login?next=${encodeURIComponent(`/product/${product.id}`)}`); return; }
    setBusy(true); setError(null);
    try {
      const result = await mutate<{ is_favorite: boolean }>(`products/${product.id}/favorite/`, { is_favorite: !favorite });
      setFavorite(result.is_favorite);
      if (!result.is_favorite) onRemoved?.();
    } catch (error) { setError(error as Error); } finally { setBusy(false); }
  }
  return <div className={expanded ? 'v2-shop-save-expanded' : 'v2-shop-save'}><button type="button" className={expanded ? 'v2-button secondary full-width' : 'v2-shop-save-button'} disabled={busy} onClick={toggle} aria-pressed={favorite} aria-label={expanded ? undefined : `${favorite ? 'Remove' : 'Save'} ${product.name}${favorite ? ' from favorites' : ' to favorites'}`}><Heart size={expanded ? 19 : 18} fill={favorite ? 'currentColor' : 'none'} aria-hidden="true" />{expanded && (busy ? 'Saving…' : favorite ? 'Saved to favorites' : 'Save to favorites')}</button>{error && <div className="v2-shop-save-error" role="alert">{error.message}</div>}</div>;
}
export function ProductCard({ product: originalProduct, variant = 'default', onRemoved }: { product: Product; variant?: 'default' | 'shop'; onRemoved?: () => void }) {
  const product = useAmazonProduct(originalProduct);
  if (!product) return <article className="v2-panel"><p>This Amazon offer needs a fresh update.</p><button className="v2-button secondary compact" onClick={() => window.location.reload()}>Refresh offers</button></article>;
  const image = safeUrl(product.thumbnail || product.main_image, '');
  if (variant === 'shop') {
    const secondaryImage = productImages(product).map(src => safeUrl(src, '')).find(src => src && src !== image);
    const onSale = !product.checkout?.configured && product.price_available !== false && product.current_price !== null && !product.is_free && Number(product.discount_percentage) > 0;
    return <article className="v2-shop-product"><div className="v2-shop-product-media"><a href={`/product/${product.id}`} className="v2-shop-product-image" aria-label={`View ${product.name}`}><CatalogImage src={image} alt={product.name} />{secondaryImage && <CatalogImage src={secondaryImage} alt="" className="v2-shop-product-secondary" />}</a>{(product.is_free || onSale) && <span className="v2-shop-product-label">{product.is_free ? 'Free offer' : `${product.discount_percentage}% off`}</span>}<FavoriteButton product={product} onRemoved={onRemoved} /></div><div className="v2-shop-product-info"><span className="v2-shop-category">{product.category !== 'merges_1_0' ? product.category_label || product.category : ''}</span><h3><a href={`/product/${product.id}`}>{product.name}</a></h3><Price product={product} /><span className="v2-shop-product-source">{product.checkout?.configured ? 'Direct checkout' : platformLabel(product.ecommerce_platform)}</span><AmazonNotices product={product} compact /></div></article>;
  }
  return <article className="v2-product-card"><a href={`/product/${product.id}`} className="v2-card-image">{image ? <img src={image} alt={product.name} loading="lazy" /> : <span className="v2-image-placeholder" aria-hidden="true">✦</span>}{product.is_free && <span className="v2-product-tag">Free</span>}{!product.is_free && Number(product.discount_percentage) > 0 && <span className="v2-product-tag">−{product.discount_percentage}%</span>}</a><div className="v2-card-body"><span className="v2-eyebrow">{product.category !== 'merges_1_0' ? product.category_label || product.category : ''}</span><h3><a href={`/product/${product.id}`}>{product.name}</a></h3><Price product={product} /><AmazonNotices product={product} compact /></div></article>;
}
export function PostCard({ post }: { post: Post }) {
  const image = safeUrl(post.cover_image, '');
  return <article className="v2-post-card"><a href={`/blog/${encodeURIComponent(post.slug)}`} className="v2-card-image">{image ? <img src={image} alt="" loading="lazy" /> : <span className="v2-image-placeholder" aria-hidden="true">✧</span>}</a><div className="v2-card-body"><div className="v2-meta"><span>{post.category || 'Community'}</span><time dateTime={post.published_at}>{dateLabel(post.published_at)}</time></div><h3><a href={`/blog/${encodeURIComponent(post.slug)}`}>{post.title}</a></h3><p className="v2-muted v2-clamp">{plainText(post.excerpt)}</p><a className="v2-arrow-link" href={`/blog/${encodeURIComponent(post.slug)}`}>Read article →</a></div></article>;
}
function Filters({ categories, category, setCategory, onSearch, placeholder }: { categories: Category[]; category: string; setCategory: (category: string) => void; onSearch: (search: string) => void; placeholder: string }) {
  return <div className="v2-filters"><div className="v2-category-tabs"><button className={!category ? 'active' : ''} onClick={() => setCategory('')}>All</button>{categories.map(option => <button key={categoryValue(option)} className={category === categoryValue(option) ? 'active' : ''} onClick={() => setCategory(categoryValue(option))}>{categoryLabel(option)}</button>)}</div><form className="v2-search" onSubmit={event => { event.preventDefault(); onSearch(String(new FormData(event.currentTarget).get('search') || '')); }}><input type="search" name="search" aria-label={placeholder} placeholder={placeholder} /><button type="submit" aria-label="Search">↗</button></form></div>;
}

type CatalogControlsProps = { value: CatalogFilter; onChange: (patch: Partial<CatalogFilter>) => void; data: CatalogResult | null };
function CatalogControls({ value, onChange, data }: CatalogControlsProps) {
  const id = useId();
  const [minPrice, setMinPrice] = useState(value.min_price);
  const [maxPrice, setMaxPrice] = useState(value.max_price);
  const [priceError, setPriceError] = useState('');
  useEffect(() => { setMinPrice(value.min_price); setMaxPrice(value.max_price); setPriceError(''); }, [value.min_price, value.max_price, value.currency]);
  // Keep price comparison only where one currency is known, without asking
  // the member to choose currencies or comparing unlike amounts.
  const currency = value.currency || (data?.facets?.currencies.length === 1 ? data.facets.currencies[0].value : '');
  return <div className="v2-shop-filter-groups">
    <fieldset><legend>Category</legend><label className="v2-shop-choice"><input type="radio" name={`${id}-category`} checked={!value.category} onChange={() => onChange({ category: '' })} /><span>All products</span>{data?.total_count !== undefined && <small>{data.total_count}</small>}</label>{(data?.categories || []).filter(option => categoryValue(option) !== 'merges_1_0').map(option => <label className="v2-shop-choice" key={categoryValue(option)}><input type="radio" name={`${id}-category`} checked={value.category === categoryValue(option)} onChange={() => onChange({ category: categoryValue(option) })} /><span>{categoryLabel(option)}</span>{typeof option !== 'string' && option.count !== undefined && <small>{option.count}</small>}</label>)}</fieldset>
    {currency && <fieldset><legend>Price ({currency})</legend><form onSubmit={event => { event.preventDefault(); const error = priceRangeError(minPrice, maxPrice); setPriceError(error); if (!error) onChange({ currency, min_price: minPrice, max_price: maxPrice }); }}><div className="v2-shop-price-range"><label className="v2-shop-field"><span>Min</span><input type="number" min="0" step="any" inputMode="decimal" placeholder="0" value={minPrice} onChange={event => setMinPrice(event.target.value)} aria-describedby={priceError ? `${id}-price-error` : undefined} /></label><span aria-hidden="true">—</span><label className="v2-shop-field"><span>Max</span><input type="number" min="0" step="any" inputMode="decimal" placeholder="Any" value={maxPrice} onChange={event => setMaxPrice(event.target.value)} aria-describedby={priceError ? `${id}-price-error` : undefined} /></label></div>{priceError && <p id={`${id}-price-error`} role="alert" className="v2-shop-field-error">{priceError}</p>}<button type="submit" className="v2-button secondary compact v2-shop-apply-price">Apply price</button></form></fieldset>}
    {!!data?.facets?.platforms.length && <fieldset><legend>Store</legend><label className="v2-shop-choice"><input type="radio" name={`${id}-platform`} checked={!value.platform} onChange={() => onChange({ platform: '' })} /><span>All stores</span></label>{data.facets.platforms.map(option => <label className="v2-shop-choice" key={option.value}><input type="radio" name={`${id}-platform`} checked={value.platform === option.value} onChange={() => onChange({ platform: option.value })} /><span>{option.label}</span><small>{option.count}</small></label>)}</fieldset>}
    {!!data?.facets?.offers.length && <fieldset><legend>Offers</legend>{data.facets.offers.map(option => <label className="v2-shop-choice" key={option.value}><input type="checkbox" checked={value.offer === option.value} onChange={() => onChange({ offer: value.offer === option.value ? '' : option.value })} /><span>{option.label}</span><small>{option.count}</small></label>)}</fieldset>}
  </div>;
}
function CatalogSkeleton() {
  return <div className="v2-shop-skeleton" role="status"><span className="v2-shop-sr-only">Loading products…</span>{Array.from({ length: 6 }, (_, index) => <div className="v2-shop-skeleton-card" key={index} aria-hidden="true"><div /><span /><span /><span /></div>)}</div>;
}
function MobileFilters({ open, close, value, onChange, data, reset }: CatalogControlsProps & { open: boolean; close: () => void; reset: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  useEffect(() => {
    if (!open || !dialog.current) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const bodyOverflow = document.body.style.overflow;
    const element = dialog.current;
    element.showModal();
    document.body.style.overflow = 'hidden';
    const media = window.matchMedia('(min-width: 901px)');
    const resize = () => { if (media.matches) close(); };
    media.addEventListener('change', resize);
    return () => { element.close(); document.body.style.overflow = bodyOverflow; media.removeEventListener('change', resize); previous?.focus(); };
  }, [open, close]);
  // Native modal dialogs provide focus containment and Escape handling.
  return <dialog ref={dialog} className="v2-shop-filter-dialog" aria-labelledby={title} onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}><div className="v2-shop-dialog-content"><div className="v2-shop-dialog-heading"><div><span className="v2-eyebrow">Find your next favorite</span><h2 id={title}>Filters</h2></div><button type="button" className="v2-shop-icon-button" onClick={close} aria-label="Close filters" autoFocus><X size={22} /></button></div><CatalogControls value={value} onChange={onChange} data={data} /><div className="v2-shop-dialog-actions"><button className="v2-text-button" onClick={reset}>Reset filters</button><button className="v2-button compact" onClick={close}>View products <ArrowUpRight size={17} aria-hidden="true" /></button></div></div></dialog>;
}
export function StorePage({ initialCategory = '', favorites = false }: { initialCategory?: string; favorites?: boolean }) {
  const { user, sessionLoading, sessionError } = useSite();
  const [filter, setFilter] = useState<CatalogFilter>({ ...emptyCatalogFilter, category: initialCategory });
  const [ready, setReady] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [catalog, setCatalog] = useState<CatalogResult | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const read = () => { const next = catalogFilterFromQuery(new URLSearchParams(window.location.search), initialCategory); setFilter(next); setSearchInput(next.search); setReady(true); };
    read(); window.addEventListener('popstate', read); return () => window.removeEventListener('popstate', read);
  }, [initialCategory]);
  const products = useResource<CatalogResult>(!ready || (favorites && !user) ? null : `${favorites ? 'favorites' : 'products'}/?${catalogQuery(filter)}`);
  useEffect(() => { if (products.data) setCatalog(products.data); }, [products.data]);
  function change(patch: Partial<CatalogFilter>) {
    const next = { ...filter, ...patch, page: patch.page || 1 };
    setFilter(next);
    const query = catalogQuery(next, initialCategory);
    window.history.pushState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  }
  function reset() { setSearchInput(''); change({ ...emptyCatalogFilter }); }
  // Use the native dialog's stable close callback so filter changes do not
  // interrupt focus containment while the drawer is open.
  const closeFilters = useCallback(() => setMobileOpen(false), []);
  const count = filterCount(filter);
  const categoryName = (catalog?.categories || []).find(option => categoryValue(option) === filter.category);
  const currencies = catalog?.facets?.currencies || [];
  const displayCategory = categoryName ? categoryLabel(categoryName) : filter.category;
  const chips: { key: string; label: string; remove: Partial<CatalogFilter> }[] = [
    ...(filter.search ? [{ key: 'search', label: `“${filter.search}”`, remove: { search: '' } }] : []),
    ...(filter.category && filter.category !== 'merges_1_0' ? [{ key: 'category', label: displayCategory, remove: { category: '' } }] : []),
    ...(filter.platform ? [{ key: 'platform', label: platformLabel(filter.platform), remove: { platform: '' } }] : []),
    ...(filter.offer ? [{ key: 'offer', label: filter.offer === 'free' ? 'Free offers' : 'On sale', remove: { offer: '' } }] : []),
    ...(filter.currency ? [{ key: 'currency', label: filter.currency, remove: { currency: '', min_price: '', max_price: '', sort: filter.sort.startsWith('price_') ? 'newest' : filter.sort } }] : []),
    ...(filter.min_price || filter.max_price ? [{ key: 'price', label: `${filter.min_price || '0'} – ${filter.max_price || 'Any'} ${filter.currency}`, remove: { min_price: '', max_price: '' } }] : []),
  ];
  return <div className="v2-container v2-page v2-shop-page">{favorites && <AccountNav active="favorites" />}<header className="v2-shop-heading"><div><span className="v2-eyebrow">{favorites ? 'Your collection' : 'The Transformers collection'}</span><h1>{favorites ? 'Saved products' : 'Find your next favorite.'}</h1><p>{favorites ? 'The discoveries you want to come back to.' : 'Collectibles, creative tools, and discoveries from our community.'}</p></div>{!favorites && <a href="/favorites" className="v2-shop-saved-link"><Heart size={18} aria-hidden="true" />Saved products</a>}</header>{favorites && !user ? <>{sessionLoading ? <Loading /> : <Notice><a href="/login?next=/favorites">Sign in</a> to see your saved products.</Notice>}<ErrorNotice error={sessionError} /></> : <>
    {!favorites && <FeaturedShopRequests />}
    <nav className="v2-shop-categories" aria-label="Product categories"><button aria-pressed={!filter.category} className={!filter.category ? 'active' : ''} onClick={() => change({ category: '' })}>All products</button>{(catalog?.categories || []).filter(option => categoryValue(option) !== 'merges_1_0').map(option => <button key={categoryValue(option)} aria-pressed={filter.category === categoryValue(option)} className={filter.category === categoryValue(option) ? 'active' : ''} onClick={() => change({ category: categoryValue(option) })}>{categoryLabel(option)}</button>)}</nav>
    <div className="v2-shop-toolbar"><h2 ref={resultHeading} tabIndex={-1}>{filter.category && filter.category !== 'merges_1_0' ? displayCategory : favorites ? 'Your favorites' : 'All products'}<span aria-live="polite">{products.data ? ` (${products.data.count})` : ''}</span></h2><form className="v2-shop-search" role="search" onSubmit={event => { event.preventDefault(); change({ search: searchInput.trim() }); }}><input type="search" name="search" aria-label="Search products" placeholder="Search the collection" value={searchInput} onChange={event => setSearchInput(event.target.value)} /><button type="submit" aria-label="Search products"><Search size={19} /></button></form><button className="v2-button secondary compact v2-shop-filter-toggle" onClick={() => setMobileOpen(true)} aria-haspopup="dialog" aria-expanded={mobileOpen}><SlidersHorizontal size={17} aria-hidden="true" />Filters{count > 0 && <span>{count}</span>}</button><label className="v2-shop-sort"><ArrowDownUp size={17} aria-hidden="true" /><span className="v2-shop-sr-only">Sort products</span><select value={filter.sort} onChange={event => change({ sort: event.target.value, ...(!filter.currency && currencies.length === 1 && event.target.value.startsWith('price_') ? { currency: currencies[0].value } : {}) })}><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="price_asc" disabled={!filter.currency && currencies.length !== 1}>Price: Low to High</option><option value="price_desc" disabled={!filter.currency && currencies.length !== 1}>Price: High to Low</option></select></label></div>
    <div className="v2-shop-layout"><aside className="v2-shop-sidebar" aria-label="Filter products"><div className="v2-shop-sidebar-heading"><h3><SlidersHorizontal size={16} aria-hidden="true" />Filters</h3>{count > 0 && <button className="v2-text-button" onClick={reset}>Reset</button>}</div><CatalogControls value={filter} onChange={change} data={catalog} /></aside><section className="v2-shop-results" aria-label="Product results" aria-busy={products.loading}>{chips.length > 0 && <div className="v2-shop-applied" aria-label="Applied filters">{chips.map(chip => <button key={chip.key} onClick={() => { if (chip.key === 'search') setSearchInput(''); change(chip.remove); }} aria-label={`Remove ${chip.label} filter`}>{chip.label}<X size={13} aria-hidden="true" /></button>)}<button className="v2-shop-clear" onClick={reset}>Clear all</button></div>}<ErrorNotice error={products.error} retry={products.reload} />{products.loading || !ready ? <CatalogSkeleton /> : products.data && <>{products.data.results.length ? <div className="v2-shop-product-grid">{products.data.results.map(product => <ProductCard key={product.id} product={product} variant="shop" onRemoved={favorites ? products.reload : undefined} />)}</div> : <div className="v2-shop-empty"><Empty title={count ? 'No matching products' : favorites ? 'Start your collection' : 'The collection is on its way'}>{count ? 'Try fewer filters or a different search to discover something new.' : favorites ? 'Tap the heart on a product to keep it here for later.' : 'New products will appear here when they are available.'}</Empty>{count ? <button className="v2-button secondary compact" onClick={reset}>Reset filters</button> : favorites && <a href="/store" className="v2-button compact">Explore the store <ArrowUpRight size={17} aria-hidden="true" /></a>}</div>}<Pagination page={products.data.page} pages={products.data.pages} onPage={page => { change({ page }); resultHeading.current?.focus(); resultHeading.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }); }} /></>}</section></div><MobileFilters open={mobileOpen} close={closeFilters} value={filter} onChange={change} data={catalog} reset={reset} />
  </>}</div>;
}

function ProductContent({ product: originalProduct }: { product: Product }) {
  const freshProduct = useAmazonProduct(originalProduct);
  const product = freshProduct || originalProduct;
  const images = productImages(product).map(image => safeUrl(image, '')).filter(Boolean);
  const [imageIndex, setImageIndex] = useState(0);
  const activeIndex = Math.min(imageIndex, Math.max(0, images.length - 1));
  const activeImage = images[activeIndex] || '';
  const related = useResource<PageResult<Product>>(freshProduct ? `products/?${new URLSearchParams({ category: product.category })}` : null);
  const relatedProducts = related.data?.results.filter(item => item.id !== product.id).slice(0, 3) || [];
  const purchaseUrl = safeUrl(product.redirect_url, '');
  const videoUrl = safeUrl(product.video_url, '');
  const onSale = !product.checkout?.configured && product.price_available !== false && product.current_price !== null && !product.is_free && Number(product.discount_percentage) > 0;
  if (!freshProduct) return <Empty title="This Amazon offer needs a fresh update"><button className="v2-button secondary" onClick={() => window.location.reload()}>Refresh offer</button></Empty>;
  return <>
    <div className="v2-shop-detail">
      <section className="v2-shop-gallery" aria-label="Product images">
        <div className="v2-shop-gallery-stage">
          <CatalogImage src={activeImage} alt={`${product.name}${images.length > 1 ? ` — image ${activeIndex + 1}` : ''}`} priority />
          {(product.is_free || onSale) && <span className="v2-shop-product-label">{product.is_free ? 'Free offer' : `${product.discount_percentage}% off`}</span>}
          {images.length > 1 && <div className="v2-shop-gallery-controls"><button type="button" className="v2-shop-icon-button" aria-label="Previous product image" onClick={() => setImageIndex((activeIndex - 1 + images.length) % images.length)}><ChevronLeft size={20} /></button><span aria-live="polite">{activeIndex + 1} / {images.length}</span><button type="button" className="v2-shop-icon-button" aria-label="Next product image" onClick={() => setImageIndex((activeIndex + 1) % images.length)}><ChevronRight size={20} /></button></div>}
        </div>
        {images.length > 1 && <div className="v2-shop-gallery-thumbnails" aria-label="Choose product image">{images.map((image, index) => <button type="button" key={image} className={activeIndex === index ? 'active' : ''} onClick={() => setImageIndex(index)} aria-label={`View product image ${index + 1}`} aria-pressed={activeIndex === index}><CatalogImage src={image} alt="" /></button>)}</div>}
        {videoUrl && <a className="v2-shop-video" href={videoUrl} target="_blank" rel="noopener noreferrer">Watch product video <ArrowUpRight size={17} aria-hidden="true" /></a>}
      </section>
      <section className="v2-shop-product-summary" aria-labelledby="product-title">
        <a className="v2-eyebrow" href={`/store?category=${encodeURIComponent(product.category)}`}>{product.category !== 'merges_1_0' ? product.category_label || product.category : ''}</a>
        <h1 id="product-title">{product.name}</h1>
        <div className="v2-shop-detail-price"><Price product={product} />{onSale && <span className="v2-shop-saving">Save {product.discount_percentage}%</span>}</div>
        <p className="v2-shop-detail-source">{product.checkout?.configured ? 'Available through 2.0Transformers' : purchaseUrl ? `Available from ${platformLabel(product.ecommerce_platform)}` : 'From the community collection'}</p>
        {product.is_free && product.free_deadline && <p className="v2-shop-offer-deadline">Free offer ends {dateLabel(product.free_deadline)}.</p>}
        <div className="v2-shop-purchase-actions">
          {product.checkout?.configured ? <CheckoutButton product={product} /> : purchaseUrl ? <a href={purchaseUrl} target="_blank" rel={product.ecommerce_platform === 'amazon' ? 'sponsored noopener noreferrer' : 'noopener noreferrer'} className="v2-button full-width">{product.is_free ? 'Get this offer' : 'View offer'}{product.ecommerce_platform && product.ecommerce_platform !== 'none' ? ` on ${platformLabel(product.ecommerce_platform)}` : ''}<ArrowUpRight size={19} aria-hidden="true" /></a> : <Notice>A purchase link is not available for this product yet.</Notice>}
          <FavoriteButton product={product} expanded />
        </div>
        {product.checkout?.configured ? <p className="v2-shop-purchase-note"><ShieldCheck size={19} aria-hidden="true" /><span>Secure checkout with Stripe. Track payment confirmation in <a href="/account/orders">your orders</a>.</span></p> : purchaseUrl && <p className="v2-shop-purchase-note"><ArrowUpRight size={18} aria-hidden="true" /><span>You’ll complete your purchase on the linked store.</span></p>}
        {product.description && <details className="v2-shop-detail-section" open><summary>About this product<ChevronDown size={18} aria-hidden="true" /></summary><RichText html={product.description} /></details>}
        {product.checkout?.configured && product.checkout.fulfillment_note && <details className="v2-shop-detail-section" open><summary>Order information<ChevronDown size={18} aria-hidden="true" /></summary><p>{product.checkout.fulfillment_note}</p></details>}
        {product.amazon_automated && <div className="v2-shop-amazon-details"><AmazonNotices product={product} /></div>}
      </section>
    </div>
    {!!relatedProducts.length && <section className="v2-shop-related" aria-labelledby="related-products-title"><div className="v2-section-heading"><div><span className="v2-eyebrow">Keep exploring</span><h2 id="related-products-title">More from this collection</h2></div><a href={`/store?category=${encodeURIComponent(product.category)}`} className="v2-arrow-link">View collection <ArrowUpRight size={19} aria-hidden="true" /></a></div><div className="v2-shop-product-grid">{relatedProducts.map(item => <ProductCard key={item.id} product={item} variant="shop" />)}</div></section>}
  </>;
}
export function ProductPage({ id }: { id: string }) {
  const product = useResource<{ product: Product }>(`products/${encodeURIComponent(id)}/`);
  return <div className="v2-container v2-page v2-shop-detail-page"><nav className="v2-shop-breadcrumbs" aria-label="Breadcrumb"><a href="/store">Store</a>{product.data && <><ChevronRight size={14} aria-hidden="true" /><a href={`/store?category=${encodeURIComponent(product.data.product.category)}`}>{product.data.product.category_label || product.data.product.category}</a><ChevronRight size={14} aria-hidden="true" /><span aria-current="page">{product.data.product.name}</span></>}</nav><ErrorNotice error={product.error} retry={product.reload} />{product.loading && <Loading label="Loading product…" />}{product.data && <ProductContent key={product.data.product.id} product={product.data.product} />}</div>;
}
export function BlogPage({ initialCategory = '' }: { initialCategory?: string }) {
  const [category, setCategory] = useState(initialCategory);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const posts = useResource<PageResult<Post>>(`blog/?${new URLSearchParams({ category, search, page: String(page) })}`);
  return <div className="v2-container v2-page"><PageHeading eyebrow="Ideas, inspiration & updates" title="Our Blog"><p>Stories from the community and beyond.</p></PageHeading><Filters categories={posts.data?.categories || []} category={category} setCategory={value => { setCategory(value); setPage(1); }} onSearch={value => { setSearch(value); setPage(1); }} placeholder="Search articles" /><ErrorNotice error={posts.error} retry={posts.reload} />{posts.loading && <Loading label="Loading articles…" />}{posts.data && <>{posts.data.results.length ? <div className="v2-card-grid">{posts.data.results.map(post => <PostCard key={post.id} post={post} />)}</div> : <Empty title="No articles yet">{category || search ? 'Try a different search or category.' : 'New stories will appear here when published.'}</Empty>}<Pagination page={posts.data.page} pages={posts.data.pages} onPage={setPage} /></>}</div>;
}
export function PostPage({ slug }: { slug: string }) {
  const post = useResource<{ post: Post }>(`blog/${encodeURIComponent(slug)}/`);
  return <div className="v2-container v2-page"><a href="/blog" className="v2-back-link">← Back to blog</a><ErrorNotice error={post.error} retry={post.reload} />{post.loading && <Loading label="Loading article…" />}{post.data && <article className="v2-article"><PageHeading eyebrow={post.data.post.category} title={post.data.post.title}><p>{post.data.post.author}{post.data.post.author ? ' · ' : ''}{dateLabel(post.data.post.published_at)}</p></PageHeading>{safeUrl(post.data.post.cover_image, '') && <img className="v2-article-image" src={safeUrl(post.data.post.cover_image)} alt="" />}<RichText html={post.data.post.body} /></article>}</div>;
}


