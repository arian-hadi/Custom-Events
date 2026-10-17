# Featured shop requests

The `/store` and category pages display backend-managed request cards above the
product filters. Sorting, searches, and pagination never move these cards. Saved
products do not include this section.

Apply normal Django migrations. Shop migrations 0013–0014 create the model and
seed Edit Request and Media Request as visible placeholders. No real purchases
are enabled by the seed. There is no hardcoded frontend fallback: hiding every
card in admin removes the section.

In **Django admin → Shop → Featured shop requests**, edit the title, description,
expanded details, optional image, icon, badge, price wording, turnaround, button
labels, Buy Me a Coffee URL, visibility, and display order. Descriptions and details
are plain text. Lower display order appears first.

To launch a request, replace the sample copy, set accurate pricing and delivery
information, paste its HTTPS Buy Me a Coffee listing URL, and uncheck **Is
placeholder**. The admin validates the link before allowing this. While placeholder
mode is on, the public API withholds the link and the card button is disabled.
Use **Is active** to hide a card, or change display order in the admin list.

Changes appear on the next page load without rebuilding the frontend. Purchase
links open Buy Me a Coffee in a new tab. Prices and availability are manually
maintained; this feature does not synchronize products or record payments, and
does not alter the existing product checkout flows.

Public read-only endpoint: `/api/v2/shop/featured-requests/`.
