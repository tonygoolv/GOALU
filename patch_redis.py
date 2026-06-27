import os
import json
import fakeredis.aioredis
from seed_dummy_data import PRODUCTS, MARGIN_EUR

def patch_app_py():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Remove duplicate mounts
    content = content.replace("app.mount('/static', StaticFiles(directory='static'), name='static')\ntemplates = Jinja2Templates(directory='templates')\n", "")
    content = content.replace("from fastapi.templating import Jinja2Templates\nfrom fastapi.staticfiles import StaticFiles\n", "", 1)

    # Inject the lifespan for fakeredis
    injection_code = """
import fakeredis.aioredis
from contextlib import asynccontextmanager
import sys

fake_redis_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global fake_redis_instance
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    try:
        r = aioredis.Redis(host=redis_host, port=redis_port, socket_timeout=1)
        await r.ping()
        await r.aclose()
        print("Connected to real Redis")
    except Exception:
        print("Real Redis not found. Using FakeRedis and seeding data...", file=sys.stderr)
        fake_redis_instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
        # Seed dummy data
        from seed_dummy_data import PRODUCTS, MARGIN_EUR
        for prod in PRODUCTS:
            url = prod['scraped_url']
            final_price = prod['original_price_eur'] + MARGIN_EUR
            payload = {
                "scraped_url": url,
                "title": prod['title'],
                "original_price_eur": prod['original_price_eur'],
                "final_price_eur": final_price,
                "description": prod['description'],
                "image_urls": prod['image_urls'],
                "status": "SAFE",
                "country": prod['country']
            }
            await fake_redis_instance.set(url, json.dumps(payload), ex=1800)
    yield

def get_redis():
    global fake_redis_instance
    if fake_redis_instance:
        return fake_redis_instance
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    return aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)

"""
    if "fake_redis_instance" not in content:
        content = content.replace('app = FastAPI(title="GOALU | National Team Football Jerseys")', injection_code + '\napp = FastAPI(title="GOALU | National Team Football Jerseys", lifespan=lifespan)')

    # Replace aioredis.Redis with get_redis()
    content = content.replace("r = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)", "r = get_redis()")
    content = content.replace("r = aioredis.Redis(host=redis_host, port=redis_port)", "r = get_redis()")
    
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(content)

def patch_workers_py():
    with open("workers.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # We don't need to patch workers.py heavily since it connects to redis, but it's a separate process usually.
    # If it's just for local development UI testing, workers.py isn't actively running.
    # We will just write a wrapper around aioredis.Redis.
    pass

if __name__ == '__main__':
    patch_app_py()
    print("Patched app.py")
