# V2 League and Shop redesign

Current league scope (10 October 2026): open calendar-month leagues supported by weekly competitions. Annual competition is retired; historical records are preserved. See [the current league plan](EDITING_LEAGUE_IMPLEMENTATION_PLAN.md).

This change updates the Editing Hub, shop listing, favorites listing, and product detail pages on `version-2.0`. It reuses the existing Django domains, session authentication, checkout, and Next.js site shell. The member dashboard and other site sections retain their existing layouts.

## Design references

- [Formula 1 results](https://www.formula1.com/en/results/2026/drivers): season/round context, standings hierarchy, and clear result rows.
- [Nike product listing](https://www.nike.com/tr/w/yeni-cikanlar-3n82y): category navigation, sidebar/mobile filters, image-first product cards, and gallery/detail hierarchy.

These are structural references. Both sections use the website's existing dark surfaces, configurable red accent, fonts, buttons, radii, and navigation. New styles are scoped in `New_Frontend/app/league-hub.css` and `New_Frontend/app/shop-catalog.css`.

## Editing Hub

- Monthly league and individual round results, with calendar year, month and round archive selectors.
- Search by editor/channel and filter by platform while preserving authoritative positions, including ties.
- Current member highlighting, verified channel identity, official league points, latest result, and scored round count where available.
- Weekly scores remain distinct from awarded league points. Provisional results are labelled; unavailable scores and ranks remain neutral.
- Compact signed-in member summary, competition calendar and history, finalized weekly/monthly highlights, and scoring explanations.
- Existing submit, replace, withdraw, validation status, and score breakdown flows are retained.
- Successful data stays visible during background refreshes, without resetting an in-progress entry form.

No follower-count rankings are used. Rank movement is displayed only when supplied by the API; the current backend returns `null`, so no movement is invented. There are no invented tiers or achievements.

The API adds `GET /api/v2/league/rounds/?year=2026` and enriches standings with public channel/profile and latest-result metadata. Live standings serialize public score fields, respect authoritative placement, and exclude private queued submissions. Finalized results continue to require eligible, calibrated scoring configuration.

## Shop

- Category navigation, search, result counts, applied filter chips, and reset actions.
- Desktop sidebar and keyboard-accessible native mobile filter dialog.
- Newest/oldest and price sorting, with real category, store, currency, price range, and offer filters.
- URL-backed filter state, including browser back/forward behavior.
- Image-led product cards, available secondary images, real free/discount labels, favorites, and missing-image fallbacks.
- Product detail gallery, product information, purchase/save actions, and related products from the same actual category.
- Existing Stripe checkout, external store destinations, Amazon attribution, and offer expiry behavior are preserved.

Catalog filters apply to both `products/` and authenticated `favorites/`. Supported query fields are `category`, `search`, `sort`, `platform`, `offer`, `currency`, `min_price`, `max_price`, and `page`. Sort values are `newest`, `oldest`, `price_asc`, and `price_desc`; offer values are `sale` and `free`. Responses include counted categories and store/currency/offer facets.

Price comparisons require one currency. SQL filtering uses the same effective pricing as public product display: configured Stripe amounts, fresh Amazon offers, and current legacy discounts/free windows. Stale Amazon prices are not used for price comparisons.

The existing model does not provide stock, size/color variants, character/brand facets, popularity, or sales rankings. Those controls are intentionally absent. Related products mean same-category products, not personalized recommendations. External-store purchases remain managed by those stores.

## Setup and validation

No new secrets, environment variables, database migrations, or external services are required by this redesign. Existing Stripe/Amazon setup requirements are unchanged. Local validation uses `prime_project.settings_v2_local` and the frontend dev server; Docker remains deferred at the user's request.

Validated on October 3, 2026:

- `npm run build`: successful production build, including TypeScript.
- `npm test`: 41 frontend tests passed (catalog, league, commerce, and member dashboard).
- `.venv\Scripts\python.exe prime_project/manage.py test platform_api edithub shop.test_amazon shop.test_payments --settings=prime_project.test_settings --noinput`: 122 tests passed, including 16 discovery API tests.
- `npm run verify`: 21 pages, 15 assets, public APIs, private access guards, and CSRF checks passed through the local frontend proxy.
- Browser checks at desktop, 820px tablet, and 390px mobile widths: standings fit without horizontal page overflow; latest results remain available on mobile; shop filtering/sorting and browser Back restore state; native drawer focus containment/Escape return work; gallery images switch; anonymous favorites preserve the product return destination; unconfigured checkout stays disabled.

The local league has no published rounds, so live empty states were checked against the API. Populated standings screenshots use an explicitly labelled, static render of the real component with sample scores. Automated renderer/API tests cover actual data contracts; the populated screenshot is not evidence of a completed real competition.

Shop preview screenshots include three clearly named temporary QA products. Those records and copied images were removed after verification. Existing local products, accounts, and configuration were preserved. The temporary public league fixture was also removed.

Lint is not a clean gate in this checkout: the focused check still reports Next image/link conventions, React effect-state patterns, and semantic-role/test-promise rules. The runtime tests, type checks, and production build pass. Live payment execution and Amazon provider calls were not exercised during this visual redesign; their existing mocked integration tests pass. Docker/deployment validation remains deferred.

## Preview captures

- [Shop desktop](previews/shop-desktop.jpg), [mobile](previews/shop-mobile.jpg), and [mobile filters](previews/shop-mobile-filters.jpg).
- [Product detail desktop](previews/shop-product-desktop.jpg) and [mobile](previews/shop-product-mobile.jpg).
- [League live empty state](previews/league-empty-desktop.jpg) and [mobile](previews/league-empty-mobile.jpg).
- [League populated visual fixture](previews/league-populated-desktop.jpg) and [mobile](previews/league-populated-mobile.jpg).
