import os
import json
import smtplib
import redis.asyncio as aioredis
import stripe
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


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
        await asyncio.wait_for(r.ping(), timeout=1.0)
        await r.aclose()
        print("Connected to real Redis")
    except Exception as e:
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


app = FastAPI(title="GOALU | National Team Football Jerseys", lifespan=lifespan)


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def send_order_email_to_admin(metadata: dict):
    """
    Formats the order details and shipping information into an email,
    sending it to the administrator immediately.
    """
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    admin_email = os.environ.get("ADMIN_EMAIL")
    
    # Fallback log in case SMTP credentials are not yet set up
    if not all([smtp_server, smtp_port, smtp_username, smtp_password, admin_email]):
        print("WARNING: SMTP server credentials or admin email not fully configured. Order details logged below:")
        print(json.dumps(metadata, indent=2))
        return

    # Extract customer and product details from metadata
    c_name = metadata.get('customer_name', 'N/A')
    c_email = metadata.get('customer_email', 'N/A')
    s_street = metadata.get('shipping_street', 'N/A')
    s_city = metadata.get('shipping_city', 'N/A')
    s_postal_code = metadata.get('shipping_postal_code', 'N/A')
    s_country = metadata.get('shipping_country', 'N/A')
    p_url = metadata.get('product_url', 'N/A')
    p_title = metadata.get('product_title', 'N/A')
    p_price = metadata.get('product_price', '0.00')

    # Construct the multipart email message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"New Order Confirmed: {p_title[:30]}..."
    msg['From'] = smtp_username
    msg['To'] = admin_email

    # Plain text version for compatibility
    text_content = f"""
    New Order Received!
    
    Product: {p_title}
    Price: €{p_price}
    AliExpress Link: {p_url}
    
    Customer Info:
    Name: {c_name}
    Email: {c_email}
    
    Shipping Address:
    Street: {s_street}
    City: {s_city}
    Postal Code: {s_postal_code}
    Country: {s_country}
    """

    # Premium HTML email version
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f4f5f7; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e4e8;">
          <div style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); padding: 30px; text-align: center; color: #ffffff;">
            <h1 style="margin: 0; font-size: 24px;">New Order Confirmed!</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">GOALU Order Notification</p>
          </div>
          <div style="padding: 30px;">
            <h2 style="font-size: 18px; border-bottom: 1px solid #e1e4e8; padding-bottom: 10px; margin-top: 0; color: #1a202c;">Product Details</h2>
            <p style="margin: 10px 0;"><strong>Title:</strong> {p_title}</p>
            <p style="margin: 10px 0;"><strong>Commission-free Price:</strong> €{p_price}</p>
            <p style="margin: 10px 0;"><strong>AliExpress Order Link:</strong> <a href="{p_url}" target="_blank" style="color: #6366f1; text-decoration: none; font-weight: bold;">Order from AliExpress &rarr;</a></p>
            
            <h2 style="font-size: 18px; border-bottom: 1px solid #e1e4e8; padding-bottom: 10px; margin-top: 30px; color: #1a202c;">Shipping Details</h2>
            <p style="margin: 10px 0;"><strong>Customer Name:</strong> {c_name}</p>
            <p style="margin: 10px 0;"><strong>Customer Email:</strong> {c_email}</p>
            <p style="margin: 10px 0;"><strong>Address:</strong><br>
               {s_street}<br>
               {s_city}, {s_postal_code}<br>
               {s_country}
            </p>
          </div>
          <div style="background-color: #f8fafc; padding: 15px; text-align: center; font-size: 12px; color: #718096; border-top: 1px solid #e1e4e8;">
            This order was processed through the GOALU platform.
          </div>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(text_content, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP(smtp_server, int(smtp_port))
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, admin_email, msg.as_string())
        print(f"SUCCESS: Order notification email sent to {admin_email}.")
    except Exception as email_err:
        print(f"ERROR: Failed to send order email via SMTP: {email_err}", file=sys.stderr)
    finally:
        try:
            server.quit()
        except Exception:
            pass

@app.get("/", response_class=HTMLResponse)
async def read_storefront(request: Request, ordered: str = None, country: str = None):
    # Fetch connection config from env variables
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    
    r = get_redis()
    try:
        # Scan/retrieve all keys (Task 2)
        keys = await r.keys("*")
        
        if not keys:
            return templates.TemplateResponse(request=request, name="storefront.html", context={"request": request, "products": [], "ordered": ordered, "country": country})
            
        # Fetch all values in one round-trip (MGET) for maximum speed (Task 5)
        raw_values = await r.mget(keys)
        
        products = []
        for val in raw_values:
            if val:
                try:
                    product_data = json.loads(val)
                    # Task 3: Filter so only SAFE products are served
                    if product_data.get("status") == "SAFE":
                        # Apply optional country filter
                        if country and product_data.get("country", "").lower() != country.lower():
                            continue
                        products.append(product_data)
                except (json.JSONDecodeError, TypeError):
                    continue
                    
        # Return response (Task 4)
        return templates.TemplateResponse(request=request, name="storefront.html", context={"request": request, "products": products, "ordered": ordered, "country": country})
        
    except Exception as e:
        return templates.TemplateResponse(request=request, name="error.html", context={"request": request, "err_msg": str(e)}, status_code=500)
    finally:
        await r.aclose()

@app.get("/checkout", response_class=HTMLResponse)
async def get_checkout(request: Request, url: str):
    """
    Renders the checkout shipping details form.
    Loads product data securely from Redis using the URL key to prevent user tampering.
    """
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    r = get_redis()
    try:
        val = await r.get(url)
        if not val:
            return templates.TemplateResponse(request=request, name="error.html", context={"request": request, "err_msg": "Product not found in active listings"}, status_code=404)
        product_data = json.loads(val)
        return templates.TemplateResponse(request=request, name="checkout.html", context={"request": request, "prod": product_data})
    except Exception as e:
        return templates.TemplateResponse(request=request, name="error.html", context={"request": request, "err_msg": str(e)}, status_code=500)
    finally:
        await r.aclose()

@app.post("/checkout")
async def post_checkout(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    street: str = Form(...),
    city: str = Form(...),
    postal_code: str = Form(...),
    country: str = Form(...),
    product_url: str = Form(...)
):
    """
    Handles form submission. Generates a Stripe Checkout Session
    and embeds customer shipping/product details in metadata.
    """
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    r = get_redis()
    try:
        val = await r.get(product_url)
        if not val:
            return templates.TemplateResponse(request=request, name="error.html", context={"request": request, "err_msg": "Product not found in active listings"}, status_code=404)
        product_data = json.loads(val)
        
        product_title = product_data.get("title", "Dropshipped Product")
        final_price = product_data.get("final_price_eur", 0.0)
        image_urls = product_data.get("image_urls", [])
        product_image = image_urls[0] if image_urls else ""
        
        stripe.api_key = os.environ.get("STRIPE_API_KEY")
        
        # Fallback simulator if Stripe configuration is missing
        if not stripe.api_key:
            print("WARNING: STRIPE_API_KEY is not configured. Simulating successful checkout...")
            mock_metadata = {
                'customer_name': name,
                'customer_email': email,
                'shipping_street': street,
                'shipping_city': city,
                'shipping_postal_code': postal_code,
                'shipping_country': country,
                'product_url': product_url,
                'product_title': product_title,
                'product_price': str(final_price)
            }
            # Route immediately to email admin (simulated webhook event completion)
            send_order_email_to_admin(mock_metadata)
            return RedirectResponse(url="/?ordered=success", status_code=303)
            
        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': product_title,
                        'images': [product_image] if product_image else [],
                    },
                    'unit_amount': int(final_price * 100), # amount in cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='http://localhost:8000/?ordered=success',
            cancel_url='http://localhost:8000/?ordered=cancel',
            # Task 4: Store shipping and product details inside session metadata to keep backend stateless!
            metadata={
                'customer_name': name,
                'customer_email': email,
                'shipping_street': street,
                'shipping_city': city,
                'shipping_postal_code': postal_code,
                'shipping_country': country,
                'product_url': product_url,
                'product_title': product_title,
                'product_price': str(final_price)
            }
        )
        return RedirectResponse(url=session.url, status_code=303)
    except Exception as e:
        return templates.TemplateResponse(request=request, name="error.html", context={"request": request, "err_msg": f"Failed to initiate transaction: {e}"}, status_code=500)
    finally:
        await r.aclose()

@app.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Receives Stripe webhooks. Confirms checkout completion,
    triggers admin email notify, and does not save any data.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    stripe.api_key = os.environ.get("STRIPE_API_KEY")

    event = None
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        else:
            data = json.loads(payload)
            event = stripe.Event.construct_from(data, stripe.api_key)
    except Exception as e:
        print(f"Webhook signature verification failed: {e}", file=sys.stderr)
        return HTMLResponse(content=str(e), status_code=400)

    # Listen for completed checkout events
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        # Route details to email (no database write, no log of customer data)
        send_order_email_to_admin(metadata)
        
    return {"status": "success"}
