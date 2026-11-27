"""RefurbPhone shopping feeds for Microsoft Merchant Center.

Reads each country website's public product list (https://<domain>/products.json),
which Shopify already returns in that site's language, link handles and currency,
and writes one tab-separated feed per country in Microsoft's format.

No Shopify credentials are used. Nothing in Shopify is changed.
"""
import csv
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

# country code -> site settings. "service" is the shipping service name shown to shoppers.
COUNTRIES = {
    "nl": {"domain": "refurb-phone.nl", "currency": "EUR", "service": "Gratis verzending"},
    "be": {"domain": "refurbphone.be", "currency": "EUR", "service": "Gratis verzending"},
    "pt": {"domain": "refurbphone.pt", "currency": "EUR", "service": "Envio gratuito"},
    "fr": {"domain": "refurbphone.fr", "currency": "EUR", "service": "Livraison gratuite"},
    "es": {"domain": "refurbphone.es", "currency": "EUR", "service": "Envío gratuito"},
    "ie": {"domain": "refurbphone.ie", "currency": "EUR", "service": "Free delivery"},
    "de": {"domain": "refurbphone.de", "currency": "EUR", "service": "Gratis Versand"},
    "at": {"domain": "refurbphone.at", "currency": "EUR", "service": "Gratis Versand"},
    "dk": {"domain": "refurbphone.dk", "currency": "DKK", "service": "Gratis levering"},
    "se": {"domain": "refurbphone.se", "currency": "SEK", "service": "Fri frakt"},
    "fi": {"domain": "refurbphone.fi", "currency": "EUR", "service": "Ilmainen toimitus"},
}

HEADER = [
    "id", "item_group_id", "title", "description", "link", "image_link",
    "additional_image_link", "price", "sale_price", "availability", "condition",
    "brand", "mpn", "identifier_exists", "product_type", "shipping", "shipping_weight",
]

USER_AGENT = "RefurbPhone-feed/1.0 (+Microsoft Merchant Center feed)"
PAGE_SIZE = 250
MAX_PAGES = 60


def fetch_json(url, tries=5):
    """GET a JSON URL, backing off on rate limits and server errors."""
    delay = 5
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"giving up on {url}")


def all_products(domain):
    products = []
    for page in range(1, MAX_PAGES + 1):
        data = fetch_json(f"https://{domain}/products.json?limit={PAGE_SIZE}&page={page}")
        batch = data.get("products", [])
        products.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(1)  # be gentle with the storefront
    return products


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def plain_text(body_html, limit=5000):
    text = TAG_RE.sub(" ", body_html or "")
    text = SPACE_RE.sub(" ", html.unescape(text)).strip()
    return text[:limit]


def clean(value):
    """Tabs and line breaks would break the TSV."""
    return SPACE_RE.sub(" ", str(value or "")).strip()


def money(amount, currency):
    return f"{float(amount):.2f} {currency}"


def rows_for(cc, cfg, products):
    country = cc.upper()
    cur = cfg["currency"]
    shipping = f"{country}::{cfg['service']}:{money(0, cur)}"
    for p in products:
        images = [i.get("src") for i in p.get("images") or [] if i.get("src")]
        desc = plain_text(p.get("body_html")) or clean(p.get("title"))
        for v in p.get("variants") or []:
            price = v.get("price")
            if price in (None, "") or float(price) <= 0:
                continue  # Microsoft rejects items without a price
            img = (v.get("featured_image") or {}).get("src") or (images[0] if images else "")
            if not img:
                continue  # Microsoft rejects items without an image
            extra = [u for u in images if u != img][:10]
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(price):
                list_price, sale = money(compare, cur), money(price, cur)
            else:
                list_price, sale = money(price, cur), ""
            title = clean(p.get("title"))
            vt = clean(v.get("title"))
            if vt and vt.lower() != "default title":
                title = f"{title} - {vt}"
            grams = v.get("grams") or 0
            yield [
                f"{cc}_{v['id']}",
                f"{cc}_{p['id']}",
                title[:150],
                clean(desc),
                f"https://{cfg['domain']}/products/{p['handle']}?variant={v['id']}",
                img,
                ",".join(extra),
                list_price,
                sale,
                "in stock" if v.get("available") else "out of stock",
                "refurbished",
                clean(p.get("vendor")),
                clean(v.get("sku")),
                "no",
                clean(p.get("product_type")),
                shipping,
                f"{grams / 1000:.2f} kg" if grams else "",
            ]


def build_feed(cc):
    cfg = COUNTRIES[cc]
    products = all_products(cfg["domain"])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(HEADER)
    n = 0
    for row in rows_for(cc, cfg, products):
        w.writerow(row)
        n += 1
    return buf.getvalue(), {"products": len(products), "items": n}


if __name__ == "__main__":
    import sys
    for code in sys.argv[1:] or ["se"]:
        text, stats = build_feed(code)
        out = os.path.join("out", f"{code}.tsv")
        os.makedirs("out", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(code, stats)
