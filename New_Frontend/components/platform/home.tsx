'use client';

import { safeUrl, useResource, type PageResult, type Post, type Product, type SiteSection } from '@/lib/api';
import { useSite } from './site-shell';
import { CollectionOrbit, HomeReveal } from './home-effects';
import { HomeHero } from './home-hero';
import { Empty, ErrorNotice, Loading } from './ui';
import { PostCard, ProductCard } from './catalog';
import { WinnerCard } from './league';
import type { LeagueWinners } from '@/lib/league-view';

const leftArtwork = [
  ['image-02', 'fd715b61f5-62b2da8704e4319fa5efad8a_Rectangle-6.png'],
  ['image-01', 'c312560d59-62b2da54527a94f7ce336471_Rectangle-5.png'],
  ['image-03', 'cdd1d6fb70-62b2da979b6d6f3ad8d0bc13_Rectangle-2.png'],
  ['image-04', '8342f4052a-62b2daa5d42435480027e70b_Rectangle-3.png'],
];
const rightArtwork = [
  ['image-05', 'a07c76b590-62b2e2264da477acb9196c77_Rectangle-7.png'],
  ['image-06', '1d5df4ed09-62b2e2332894ca8923d977d9_Rectangle-1.png'],
  ['image-07', '902bc23d83-62b2e24341d0f9ce0578ad36_Rectangle-8.png'],
  ['image-08', 'e8cb5f8458-62b2e267a74de628c97bbc93_Rectangle-4.png'],
];
export function HomePage() {
  const { site, siteLoading, siteError } = useSite();
  const products = useResource<PageResult<Product>>('products/');
  const posts = useResource<PageResult<Post>>('blog/');
  const winners = useResource<LeagueWinners>('league/winners/');
  function section(key: string, fallback: SiteSection) { return site.home_sections?.find(item => item.key === key) || fallback; }
  const access = section('access', { key: 'access', title: 'Find your next inspiration', body: 'Explore products, creative resources, and discoveries from our community.', button_text: 'Browse the Store', button_url: '/store' });
  // Events promotion is temporarily hidden; preserve its backend settings for later.
  // Original CTA: Explore events → /events.
  const communityFallback = { key: 'community', title: 'Make something together', body: 'Meet the editors, share your work, and find your place in the weekly league.', button_text: 'Meet the community', button_url: '/editing-hub' };
  const configuredCommunity = section('community', communityFallback);
  const community = /(?:^|\/)events(?:\/|$|[?#])/.test(configuredCommunity.button_url || '') ? communityFallback : configuredCommunity;
  const features = section('features', { key: 'features', title: 'Your creative space', body: 'Discover what’s happening across the community.' });
  return <div className="v2-home-content">
    <HomeHero site={site} loading={siteLoading} />
    {siteError && <div className="v2-container"><ErrorNotice error={new Error('Website settings are temporarily unavailable. Some content may not be up to date.')} /></div>}
    <div className="v2-container v2-intro-bottom"><nav className="v2-home-tabs" aria-label="Explore the homepage"><a href="#Access">Discover</a><a href="#Community">Community</a><a href="#Features">Features</a><a href="#Latest">Latest</a></nav></div>
    <HomeReveal><section className="v2-collection-section">
      <CollectionOrbit artwork={[...leftArtwork, ...rightArtwork].map(([, image]) => `/assets/${image}`)}>
        <span className="v2-eyebrow">Curated for the community</span>
        <h2>{access.title}</h2><p>{access.body}</p>
        <a href={safeUrl(access.button_url, '/store')} className="v2-arrow-link">{access.button_text || 'Explore'} <span aria-hidden="true">→</span></a>
      </CollectionOrbit>
    </section></HomeReveal>
    <HomeReveal><section className="section"><div className="base-container w-container"><div id="Community" className="v2-community"><div className="v2-community-label">Join the Community</div><div className="tab-content"><div className="description-tab-content"><h2>{community.title}</h2><p className="subtitle-tabs">{community.body}</p><a href={safeUrl(community.button_url, '/editing-hub')} className="v2-arrow-link">{community.button_text || 'Explore'} <span>→</span></a></div><div className="logo-tab-content" aria-hidden="true"><div className="image-tab-01"><img alt="" loading="lazy" src="/assets/6c01245913-62b316a9c2f0390a3c62daeb_Group-3.png" /></div><div className="image-tab-02"><img alt="" loading="lazy" src="/assets/d6af7a197b-62b316b8b2a4441e00bb8ecf_Group-4.png" /></div><div className="image-tab-03"><img alt="" loading="lazy" src="/assets/ad7745016a-62b316c5ab8b8f47a93a8315_Group-5.png" /></div></div></div></div></div></section></HomeReveal>
    <HomeReveal><section className="section features v2-home-features"><div className="base-container w-container"><div id="Features" className="features-content"><div className="heading-features"><h2>{features.title}</h2><p>{features.body}</p></div><div className="cards-features">{[
      { key: 'feature_blog', title: 'Stories & ideas', body: 'Read the latest articles, updates, and perspectives from the community.', button_url: '/blog', image: '77528ca4df-62b41adfe521e52f04b78f25_Group-8.png' },
      { key: 'feature_hub', title: 'Editing Hub', body: 'Explore weekly edits, monthly champions, and the all-time points table.', button_url: '/editing-hub', image: '73f15f5200-62b41ad7bc5d1b5196f2b4c8_Group-7.png' },
      { key: 'feature_shop', title: 'Discover the store', body: 'Browse the catalog and keep your favorite products in one place.', button_url: '/store', image: '77528ca4df-62b41adfe521e52f04b78f25_Group-8.png' },
    ].map((item) => { const content = section(item.key, item); return <a href={safeUrl(content.button_url, item.button_url)} className="card-item v2-feature-card" key={item.key}><img src={`/assets/${item.image}`} alt="" loading="lazy" className="image-card" /><h3>{content.title}</h3><p className="text-card">{content.body}</p><span className="v2-arrow-link">{content.button_text || 'Explore'} →</span></a>; })}</div></div></div></section></HomeReveal>
    <HomeReveal><section className="v2-section v2-container" id="Latest"><div className="v2-section-heading"><div><span className="v2-eyebrow">From the store</span><h2>Discover something new</h2></div><a href="/store" className="v2-arrow-link">View all →</a></div><ErrorNotice error={products.error} retry={products.reload} />{products.loading ? <Loading label="Loading products…" /> : products.data && (products.data.results.length ? <div className="v2-card-grid">{products.data.results.slice(0, 3).map(product => <ProductCard key={product.id} product={product} />)}</div> : <Empty title="The collection is on its way">Check back for new products.</Empty>)}</section></HomeReveal>
    <HomeReveal><section className="v2-section v2-container"><div className="v2-section-heading"><div><span className="v2-eyebrow">From the blog</span><h2>Stories worth sharing</h2></div><a href="/blog" className="v2-arrow-link">Read all →</a></div><ErrorNotice error={posts.error} retry={posts.reload} />{posts.loading ? <Loading label="Loading articles…" /> : posts.data && (posts.data.results.length ? <div className="v2-card-grid">{posts.data.results.slice(0, 3).map(post => <PostCard key={post.id} post={post} />)}</div> : <Empty title="More stories soon">New articles will appear here when published.</Empty>)}</section></HomeReveal>
    {(winners.data?.weekly_winner || winners.data?.monthly_winner) && <HomeReveal><section className="v2-section v2-container"><div className="v2-section-heading"><div><span className="v2-eyebrow">Community winners</span><h2>The editors setting the pace</h2></div><a href="/editing-hub#league-highlights" className="v2-arrow-link">Explore the league →</a></div><div className="v2-two-columns v2-league-showcases">{winners.data.weekly_winner && <WinnerCard title="Edit of the Week" winner={winners.data.weekly_winner} monthly={false} state={winners.data.weekly_state} loading={false} error={winners.error} retry={winners.reload} />}{winners.data.monthly_winner && <WinnerCard title="Editor of the Month" winner={winners.data.monthly_winner} monthly state={winners.data.monthly_state} loading={false} error={winners.error} retry={winners.reload} />}</div></section></HomeReveal>}
  </div>;
}

