import os

file_path = "app.py"
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if line.startswith("def get_base_html("):
        skip = True
        
    if skip and line.startswith("def send_order_email_to_admin("):
        skip = False
        
    if not skip:
        # Check for imports injection point
        if line.startswith("from fastapi.responses import HTMLResponse, RedirectResponse"):
            new_lines.append(line)
            new_lines.append("from fastapi.templating import Jinja2Templates\n")
            new_lines.append("from fastapi.staticfiles import StaticFiles\n")
            continue
            
        # Check for app injection point
        if line.startswith("app = FastAPI(title="):
            new_lines.append(line)
            new_lines.append("\napp.mount('/static', StaticFiles(directory='static'), name='static')\n")
            new_lines.append("templates = Jinja2Templates(directory='templates')\n")
            continue
            
        # Refactor read_storefront
        if "return get_storefront_html([], banner)" in line:
            new_lines.append(line.replace("return get_storefront_html([], banner)", "return templates.TemplateResponse('storefront.html', {'request': request, 'products': [], 'ordered': ordered})"))
            continue
            
        if "return get_storefront_html(products, banner)" in line:
            new_lines.append(line.replace("return get_storefront_html(products, banner)", "return templates.TemplateResponse('storefront.html', {'request': request, 'products': products, 'ordered': ordered})"))
            continue
            
        if "return get_error_html(str(e))" in line:
            new_lines.append(line.replace("return get_error_html(str(e))", "return templates.TemplateResponse('error.html', {'request': request, 'err_msg': str(e)}, status_code=500)"))
            continue
            
        if "return get_error_html(\"Product not found in active listings\")" in line:
            new_lines.append(line.replace("return get_error_html(\"Product not found in active listings\")", "return templates.TemplateResponse('error.html', {'request': request, 'err_msg': 'Product not found in active listings'}, status_code=404)"))
            continue
            
        if "return get_checkout_html(product_data)" in line:
            new_lines.append(line.replace("return get_checkout_html(product_data)", "return templates.TemplateResponse('checkout.html', {'request': request, 'prod': product_data})"))
            continue
            
        if "return get_error_html(f\"Failed to initiate transaction: {e}\")" in line:
            new_lines.append(line.replace("return get_error_html(f\"Failed to initiate transaction: {e}\")", "return templates.TemplateResponse('error.html', {'request': request, 'err_msg': f'Failed to initiate transaction: {e}'}, status_code=500)"))
            continue
            
        # Add request argument to route handlers if missing
        if "async def read_storefront(ordered: str = None):" in line:
            new_lines.append(line.replace("async def read_storefront(ordered: str = None):", "async def read_storefront(request: Request, ordered: str = None):"))
            continue
            
        if "async def get_checkout(url: str):" in line:
            new_lines.append(line.replace("async def get_checkout(url: str):", "async def get_checkout(request: Request, url: str):"))
            continue
            
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Refactoring complete.")
