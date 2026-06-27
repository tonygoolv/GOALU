import asyncio
import json
import redis.asyncio as aioredis
import os

# =============================================================================
# GOALU Seed Data — Based on real AliExpress listings (June 2025)
# Prices are AliExpress base price + €7.00 flat margin
# Product URLs and images link to actual AliExpress listings
# No trademarked brand logos (Nike, Adidas, Puma) — only country crests/flags
# =============================================================================

MARGIN_EUR = 7.00  # Flat margin per jersey

PRODUCTS = [
    {
        "country": "Argentina",
        "title": "Argentina 2025 Special Edition Soccer Jersey — Messi Fan Shirt for Men",
        "original_price_eur": 7.01,
        "description": "2025 edition Argentina home jersey inspired by the legendary Albiceleste design. Lightweight polyester with breathable mesh panels, classic sky-blue and white stripes. Perfect for matchday or casual wear.",
        "scraped_url": "https://es.aliexpress.com/item/1005010158982352.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/A72c92b83cc094ae8a1036ce63dce14041.jpg"
        ]
    },
    {
        "country": "Argentina",
        "title": "Argentina Custom Football Jersey — Personalized Name & Number for Adults & Kids",
        "original_price_eur": 12.51,
        "description": "Customizable Argentina jersey with your name and number. Premium quick-dry fabric with V-neck collar. Available in adult and kids sizes. National team colors with Argentine crest styling.",
        "scraped_url": "https://es.aliexpress.com/item/1005007795960663.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/Acc296c7a2d57478ab1b68395e38db4e1k.jpg",
            "https://ae-pic-a1.aliexpress-media.com/kf/Uba448c308f5946a58041c10eaab686d6m.jpg",
            "https://ae-pic-a1.aliexpress-media.com/kf/A5c2354ee90d14667b3eb09dbbcc4844aM.jpg",
            "https://ae-pic-a1.aliexpress-media.com/kf/Ab523c5c0976a471bb178e60f401c9a9fI.jpg"
        ]
    },
    {
        "country": "Brazil",
        "title": "Brazil Custom Football Jersey — V-Neck Breathable Shirt for Men, Women & Kids",
        "original_price_eur": 14.39,
        "description": "Iconic Seleção yellow and green design with custom name and number option. V-neck collar, breathable polyester fabric. Perfect replica-style jersey for the passionate Brazilian football fan.",
        "scraped_url": "https://es.aliexpress.com/item/1005008131188857.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/S62cf85d0e1ba456a91b8c7e84f00f8bcQ.jpg"
        ]
    },
    {
        "country": "France",
        "title": "France 2025 Soccer Jersey — Flag Graphic Football Shirt, Unisex Sports Tee",
        "original_price_eur": 6.48,
        "description": "Sleek Les Bleus jersey featuring the French tricolore flag graphic. Short-sleeve, quick-dry sports fabric. Modern slim fit suitable for training, matchday viewing, or everyday streetwear.",
        "scraped_url": "https://es.aliexpress.com/item/1005009535632357.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/Ub95b19621f264893947095fd5454bbc2n.jpg"
        ]
    },
    {
        "country": "Germany",
        "title": "Germany Personalized Soccer Jersey — Name & Number, National Team Fan Gift",
        "original_price_eur": 13.21,
        "description": "Classic Die Mannschaft white jersey with black detailing and German flag accents. Customizable with your name and number. Premium gift for football fans. Fits men, women, and kids.",
        "scraped_url": "https://es.aliexpress.com/item/1005009673873366.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/Af436201fecbb4cf09d19d8c9cc6233b2X.jpg"
        ]
    },
    {
        "country": "Spain",
        "title": "Spain 2025 Football Jersey — Summer Edition, Quick-Dry Breathable Sportswear",
        "original_price_eur": 6.93,
        "description": "La Roja home jersey in bold Spanish red with gold accents. New 2025 summer arrival with quick-dry technology. Designed for young players and adult fans alike. Breathable and lightweight.",
        "scraped_url": "https://es.aliexpress.com/item/1005012010678883.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/S908c007fd2bb4295a151413fcfcec556j.jpg"
        ]
    },
    {
        "country": "Portugal",
        "title": "Portugal Custom Jersey — Flag Design V-Neck Football Shirt for Men & Youth",
        "original_price_eur": 12.72,
        "description": "Portuguese Seleção jersey featuring the iconic red and green national colors with flag-inspired design. V-neck collar, personalized name and number. Breathable fabric for sport and casual use.",
        "scraped_url": "https://es.aliexpress.com/item/1005011991939898.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/S7353513207974162add4af9c51cca5332.jpg"
        ]
    },
    {
        "country": "Italy",
        "title": "Italy 2025 National Team Home Jersey — Azzurri Fan Edition, Breathable Outdoor Shirt",
        "original_price_eur": 8.79,
        "description": "Gli Azzurri classic blue home jersey, new 2025 fan design. Breathable outdoor fabric perfect for summer. Bold Italian blue with subtle design accents. A must-have for Serie A and Nazionale fans.",
        "scraped_url": "https://es.aliexpress.com/item/1005009212918470.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/Sb8b21dace8894caeb36e2f2b02e544ffa.jpg"
        ]
    },
    {
        "country": "Japan",
        "title": "Japan 2025 Soccer Jersey — Samurai Blue Design, Quick-Dry Sports Gift",
        "original_price_eur": 6.56,
        "description": "Samurai Blue-inspired jersey with unique Japanese cultural design elements. Breathable quick-dry technology. Perfect sports gift for youth and Japanese football culture enthusiasts.",
        "scraped_url": "https://es.aliexpress.com/item/1005011626107000.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/A4a81e21d6f624e6c88277b7127104656c.jpg"
        ]
    },
    {
        "country": "Mexico",
        "title": "Mexico 2025 3D Print Soccer Jersey — Quick-Dry Training T-Shirt for Men & Women",
        "original_price_eur": 3.99,
        "description": "El Tri jersey with stunning 3D-printed Mexico national design. Lightweight summer fabric with quick-dry technology. Great for outdoor sports training or showing your Mexican football pride.",
        "scraped_url": "https://es.aliexpress.com/item/1005009304552961.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/A4a64cf10305e4f66897a45cc5c9dbca06.jpg"
        ]
    },
    {
        "country": "Nigeria",
        "title": "Nigeria Custom Football Jersey — Breathable Quick-Dry Shirt with Name & Number",
        "original_price_eur": 12.98,
        "description": "Super Eagles jersey in Nigeria's iconic green and white. Customizable with your name and number. Quick-dry, breathable fabric for men, women, and kids. Stand out with African football style.",
        "scraped_url": "https://es.aliexpress.com/item/1005008143725469.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/S0120ce857f834d7791d3d3b828e3046ef.jpg"
        ]
    },
    {
        "country": "Netherlands",
        "title": "Netherlands Custom Football Jersey — Personalized Sportswear for Adults & Kids",
        "original_price_eur": 12.57,
        "description": "Oranje bright orange national team jersey with custom name and number. Futsal and outdoor training compatible. Breathable sports fabric with modern cut for men, women, and children.",
        "scraped_url": "https://es.aliexpress.com/item/1005009385062730.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/S781c775d9dba4f4cae3e1618df79fcd4S.jpg"
        ]
    },
    {
        "country": "England",
        "title": "England Custom Football Jersey — Breathable Shirt with Name & Number for Men & Kids",
        "original_price_eur": 12.77,
        "description": "Three Lions classic white home jersey with English flag detailing. Personalize with your name and number. Quick-dry fabric suitable for training, casual wear, and matchday support.",
        "scraped_url": "https://es.aliexpress.com/item/1005007802867453.html",
        "image_urls": [
            "https://ae-pic-a1.aliexpress-media.com/kf/S02c516e0de2c44a1b1af2a08857ac968F.jpg"
        ]
    },
]


async def seed_data():
    """Seeds Redis with real AliExpress national team jersey data + €7 margin."""
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))

    print(f"Connecting to Redis at {redis_host}:{redis_port}...")
    r = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)

    try:
        # Clear existing keys for a fresh slate
        keys = await r.keys("*")
        if keys:
            await r.delete(*keys)
            print(f"Cleared {len(keys)} existing keys.")

        for item in PRODUCTS:
            final_price = round(item["original_price_eur"] + MARGIN_EUR, 2)

            product_data = {
                "title": item["title"],
                "original_price": f"€{item['original_price_eur']:.2f}",
                "final_price_eur": final_price,
                "image_urls": item["image_urls"],
                "description": item["description"],
                "scraped_url": item["scraped_url"],
                "country": item["country"],
                "status": "SAFE"
            }

            await r.set(item["scraped_url"], json.dumps(product_data), ex=86400)  # 24h TTL
            print(f"  ✓ {item['country']:15s} | €{final_price:6.2f} | {item['title'][:60]}...")

        print(f"\nSuccessfully seeded {len(PRODUCTS)} real AliExpress jersey products into Redis!")
        print(f"Margin applied: €{MARGIN_EUR:.2f} flat per item.")

    except Exception as e:
        print(f"Error seeding data: {e}")
    finally:
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(seed_data())
