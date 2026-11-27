# RefurbPhone shopping feeds

Builds one product feed per country website for **Microsoft Merchant Center**.

The service reads each site's public product list (`https://<domain>/products.json`). Shopify already returns that list in the site's own language, with its translated links and its currency. Nothing else is needed: no Shopify keys, and nothing in Shopify is ever changed.

## Feed URLs
`https://<render-url>/feeds/<cc>.tsv`, where `<cc>` is one of `nl be pt fr es ie de at dk se fi`.

`/status` shows when each feed was last built, how many items it has, and any error.

## What's in each feed
- One row per variant (variants without a price or an image are skipped, because Microsoft rejects them). Title = product name + colour (and other options such as keyboard) + " | Refurbished" in the site language. The condition/grade option is left out of titles. If the name already says refurbished, the suffix is not repeated.
- `condition` = refurbished. `identifier_exists` = no (no GTINs).
- Shipping is free in every country, matching the Shopify "Gratis levering" EU rate. It is written in Microsoft's `country::service:price` format. Microsoft requires shipping for Germany and Austria.
- The sale price is used only when "compare at" is higher than the price.

## Refresh
Feeds rebuild on start, then every `REFRESH_HOURS` (default 4). If a build fails or comes back empty, the last good feed keeps being served.

## Settings (environment variables)
| Name | Default | Notes |
|---|---|---|
| `FEED_COUNTRIES` | all | comma list, e.g. `de,at,se,fi` |
| `REFRESH_HOURS` | 4 | |

To add a country, add a line to `COUNTRIES` in `feeds.py`.

## Run locally
`python feeds.py se fi` writes `out/se.tsv` and `out/fi.tsv`. `python server.py` serves them.
