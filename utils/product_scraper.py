"""
Scrape products from a category/listing page.
Extracts: name, price, image URL, product URL, short description.
"""

import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0)"
}


def scrape_products_from_page(url: str, max_products: int = 10, timeout: int = 15) -> list:
    """
    Scrape product listings from a category page.
    Returns list of dicts with: name, price, image_url, product_url, description
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    products = []

    # Strategy 1: JSON-LD Product schema
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            # Handle @graph arrays
            items = []
            if isinstance(data, list):
                items = data
            elif data.get("@graph"):
                items = data["@graph"]
            elif data.get("@type") == "Product":
                items = [data]
            elif data.get("@type") == "ItemList":
                items = data.get("itemListElement", [])

            for item in items:
                if isinstance(item, dict):
                    # ItemList entries have .item
                    product = item.get("item", item)
                    if not isinstance(product, dict):
                        continue
                    ptype = str(product.get("@type", ""))
                    if "Product" not in ptype:
                        continue

                    name = product.get("name", "")
                    if not name:
                        continue

                    image = product.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""
                    if isinstance(image, dict):
                        image = image.get("url", "")

                    price = ""
                    offers = product.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    if isinstance(offers, dict):
                        price = offers.get("price", "")
                        currency = offers.get("priceCurrency", "SEK")
                        if price:
                            price = f"{price} {currency}"

                    product_url = product.get("url", "")

                    products.append({
                        "name": str(name)[:100],
                        "price": str(price),
                        "image_url": str(image),
                        "product_url": str(product_url),
                        "description": str(product.get("description", ""))[:200],
                        "source": "schema",
                    })
        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    if len(products) >= max_products:
        return products[:max_products]

    # Strategy 2: HTML product cards (common patterns)
    product_selectors = [
        {"class_": re.compile(r"product[-_]?card|product[-_]?item|product[-_]?tile", re.I)},
        {"class_": re.compile(r"product[-_]?list[-_]?item", re.I)},
        {"data-product": True},
        {"class_": re.compile(r"grid[-_]?item", re.I)},
    ]

    seen_names = {p["name"].lower() for p in products}

    for selector in product_selectors:
        cards = soup.find_all(["div", "li", "article", "a"], selector)
        for card in cards[:max_products * 2]:
            # Name
            name_el = (
                card.find(["h2", "h3", "h4"], class_=re.compile(r"product[-_]?name|title", re.I))
                or card.find(["h2", "h3", "h4"])
                or card.find("a", class_=re.compile(r"product[-_]?name|title", re.I))
            )
            name = name_el.get_text(strip=True) if name_el else ""
            if not name or len(name) < 3 or name.lower() in seen_names:
                continue

            # Price
            price_el = card.find(class_=re.compile(r"price|pris", re.I))
            price = ""
            if price_el:
                price_text = price_el.get_text(strip=True)
                price_match = re.search(r"[\d\s,.]+", price_text)
                if price_match:
                    price = price_match.group().strip() + " kr"

            # Image
            img = card.find("img")
            image_url = ""
            if img:
                image_url = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(url, image_url)

            # Product URL
            link = card.find("a", href=True) if card.name != "a" else card
            product_url = ""
            if link and link.get("href"):
                product_url = link["href"]
                if not product_url.startswith("http"):
                    product_url = urljoin(url, product_url)

            # Description
            desc_el = card.find(class_=re.compile(r"description|desc|summary", re.I))
            description = desc_el.get_text(strip=True)[:200] if desc_el else ""

            products.append({
                "name": name[:100],
                "price": price,
                "image_url": image_url,
                "product_url": product_url,
                "description": description,
                "source": "html",
            })
            seen_names.add(name.lower())

            if len(products) >= max_products:
                break
        if len(products) >= max_products:
            break

    return products[:max_products]
