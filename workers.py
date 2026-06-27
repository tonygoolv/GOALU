import os
import sys
import json
import random
import asyncio
import urllib.request
import urllib.error
import redis.asyncio as aioredis
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

# List of common User-Agents for anti-bot measures
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

def calculate_markup_eur(raw_price) -> float:
    """
    Cleans the raw price string, converts it to float,
    adds a flat €7.00 profit margin,
    and returns the final price rounded to 2 decimal places.
    """
    if raw_price is None:
        raise ValueError("Raw price cannot be None")

    if isinstance(raw_price, str):
        # Remove currency symbols and space
        cleaned = raw_price.replace("€", "").replace("EUR", "").replace("$", "").replace("US", "").strip()
        
        # Handle decimal separators (Europe vs US styles)
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "," in cleaned and "." in cleaned:
            # E.g. 1,234.56 -> 1234.56
            cleaned = cleaned.replace(",", "")
            
        # Filter down to numeric characters and decimal dot
        cleaned = "".join(c for c in cleaned if c.isdigit() or c == '.')
        
        try:
            price_val = float(cleaned)
        except ValueError:
            raise ValueError(f"Could not parse price from string: {raw_price}")
    else:
        price_val = float(raw_price)

    # Markup Calculation: flat €7.00 margin
    flat_margin = 7.00
    final_price = price_val + flat_margin
    
    return round(final_price, 2)


async def verify_product_image_ip(image_url: str) -> str:
    """
    Downloads the product image and uses Gemini API (multimodal vision)
    to check for trademarked logos or official sports crests.
    Returns "FLAGGED" if trademarked IP is detected, otherwise "SAFE".
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("WARNING: GEMINI_API_KEY environment variable is not set. Skipping AI IP check and marking as SAFE.")
        return "SAFE"
        
    print(f"Downloading image for IP verification: {image_url}")
    try:
        # Request configuration to mimic browser download and bypass basic server blocks
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": random.choice(USER_AGENTS)}
        )
        # Fetch image bytes
        with urllib.request.urlopen(req, timeout=15) as response:
            img_bytes = response.read()
            # Try to grab the Content-Type header to pass correct mime type
            mime_type = response.headers.get_content_type() or "image/jpeg"
    except Exception as download_err:
        print(f"ERROR: Failed to download product image for IP verification: {download_err}", file=sys.stderr)
        return "SAFE" # Fallback to SAFE to prevent stalling the scraper pipeline

    print("Running Gemini AI Vision verification...")
    try:
        # Initialize Google GenAI client (picks up GEMINI_API_KEY from environment)
        client = genai.Client()
        
        prompt = (
            "Analyze this jersey image for trademarked sports logos (Nike, Adidas, Puma, Jordan) "
            "or official club/federation crests. If ANY official corporate or team trademark is present, "
            "reply exactly with 'FLAGGED'. If the design is completely unbranded and safe from IP infringement, "
            "reply exactly with 'SAFE'."
        )
        
        # Call gemini-2.5-flash multimodal capability
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type=mime_type,
                ),
                prompt
            ]
        )
        
        result = response.text.strip().upper()
        print(f"Gemini IP Verification Raw Output: '{result}'")
        
        # Verify result status based on model output
        if "FLAGGED" in result:
            return "FLAGGED"
        elif "SAFE" in result:
            return "SAFE"
        else:
            # Fallback in case of unexpected output format
            print(f"WARNING: Unexpected Gemini output: '{result}'. Defaulting status to SAFE.")
            return "SAFE"
            
    except Exception as api_err:
        print(f"ERROR: Gemini API call failed: {api_err}", file=sys.stderr)
        return "SAFE"

async def save_to_redis(url: str, product_data: dict):
    """
    Saves product data as a JSON string under the URL key.
    Sets TTL dynamically: 10s if the product is FLAGGED, otherwise 1800s (30m).
    """
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    
    status = product_data.get("status", "SAFE")
    # Task 4/5: Set TTL to 10 seconds if FLAGGED, else 1800 seconds (30m)
    ttl = 10 if status == "FLAGGED" else 1800
    
    print(f"Connecting to Redis at {redis_host}:{redis_port} to save scraped product data (Status: {status}, TTL: {ttl}s)...")
    r = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    try:
        json_data = json.dumps(product_data)
        # Save key with dynamic expiration
        await r.set(url, json_data, ex=ttl)
        print(f"SUCCESS: Saved AliExpress product to Redis. Key: '{url}' (Status: {status}, TTL: {ttl}s)")
    except Exception as e:
        print(f"ERROR: Failed to save data to Redis: {e}", file=sys.stderr)
    finally:
        await r.aclose()

async def scrape_aliexpress_products(urls: list) -> list:
    """
    Headless-browses each AliExpress URL asynchronously via Playwright.
    Extracts Title, Price, Image URLs, performs Gemini IP verification, and writes to Redis.
    """
    results = []
    async with async_playwright() as p:
        # Launch headless Chromium
        browser = await p.chromium.launch(headless=True)
        
        for url in urls:
            ua = random.choice(USER_AGENTS)
            print(f"Scraping URL: {url} with User-Agent: {ua}")
            
            # Browser context configuration for anti-bot
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": 1280, "height": 800},
                locale="de-DE,en-US;q=0.9",
                timezone_id="Europe/Berlin"
            )
            page = await context.new_page()
            
            # Anti-bot: Initial small wait before requesting
            await asyncio.sleep(random.uniform(1.0, 2.5))
            
            try:
                # Open page and wait until DOM is loaded
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                # Anti-bot: Scroll page slightly to trigger lazy-loads and mimic human behavior
                await page.evaluate("window.scrollTo(0, 350);")
                await asyncio.sleep(random.uniform(1.0, 2.0))
                await page.evaluate("window.scrollTo(0, 750);")
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # --- Selector Parsing ---
                
                # 1. Product Title extraction
                title = ""
                title_selectors = [
                    "h1[data-pl='product-title']",
                    "h1.item-title",
                    "h1.product-title",
                    ".product-title-text",
                    "h1"
                ]
                for sel in title_selectors:
                    elem = await page.query_selector(sel)
                    if elem:
                        text = await elem.inner_text()
                        if text and text.strip():
                            title = text.strip()
                            break
                
                # 2. Price extraction
                price_str = ""
                price_selectors = [
                    ".product-price-value",
                    ".price--current",
                    "[class*='price--current']",
                    "[class*='product-price-value']",
                    ".pdp-price",
                    ".uniform-banner-box-price"
                ]
                for sel in price_selectors:
                    elem = await page.query_selector(sel)
                    if elem:
                        text = await elem.inner_text()
                        if text and text.strip():
                            price_str = text.strip()
                            break
                            
                # 3. Main Product Image URLs extraction
                image_urls = []
                img_selectors = [
                    ".image-view-magnifier-wrap img",
                    ".magnifier-image",
                    ".magnifier-image-wrap img",
                    ".slider--img img",
                    ".product-detail-images img"
                ]
                for sel in img_selectors:
                    elements = await page.query_selector_all(sel)
                    for elem in elements:
                        src = await elem.get_attribute("src")
                        if src:
                            if src.startswith("//"):
                                src = "https:" + src
                            image_urls.append(src)
                    if image_urls:
                        break
                        
                # Fallback image search
                if not image_urls:
                    elements = await page.query_selector_all("img")
                    for elem in elements:
                        src = await elem.get_attribute("src")
                        if src and ("alicdn" in src or "product" in src) and not src.endswith(".gif"):
                            if src.startswith("//"):
                                src = "https:" + src
                            image_urls.append(src)
                            if len(image_urls) >= 5:
                                break
                                
                # Deduplicate images
                image_urls = list(dict.fromkeys(image_urls))
                
                print(f"Scraped Title: '{title}'")
                print(f"Scraped Price Raw: '{price_str}'")
                print(f"Scraped Images Found: {len(image_urls)}")
                
                # Intercept images and perform IP verification check right before saving to Redis
                if title and price_str:
                    final_price = calculate_markup_eur(price_str)
                    
                    status = "SAFE"
                    if image_urls:
                        # Task 2: Verify the main/first product image for trademark infringements
                        main_image_url = image_urls[0]
                        status = await verify_product_image_ip(main_image_url)
                    else:
                        print("WARNING: No product images found to verify. Setting status to SAFE.")
                    
                    # Task 3: Append status field
                    product_data = {
                        "title": title,
                        "original_price": price_str,
                        "final_price_eur": final_price,
                        "image_urls": image_urls,
                        "scraped_url": url,
                        "status": status
                    }
                    await save_to_redis(url, product_data)
                    results.append(product_data)
                else:
                    print(f"WARNING: Title or price missing. Skipping database save for URL: {url}")
                    
            except Exception as e:
                print(f"ERROR: Exception occurred while scraping {url}: {e}", file=sys.stderr)
            finally:
                await context.close()
                
        await browser.close()
    return results

if __name__ == "__main__":
    # Entry point for testing the module directly
    test_urls = [
        "https://www.aliexpress.com/item/1005006232742918.html"
    ]
    if len(sys.argv) > 1:
        test_urls = sys.argv[1:]
        
    print("Starting background worker AliExpress scraper run...")
    asyncio.run(scrape_aliexpress_products(test_urls))
