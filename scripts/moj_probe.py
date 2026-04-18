import time
import os
import json

# Ensure playwright is imported
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Please run: pip install playwright && playwright install chromium")
    exit(1)

def run():
    print("Starting MOJ Real Estate Bourse Probe...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        api_endpoints_found = []

        def handle_request(request):
            """Log important API requests and their payloads"""
            url = request.url.lower()
            if "api" in url or "graphql" in url or "indicator" in url or "srem" in url:
                if request.resource_type in ["fetch", "xhr"]:
                    entry = {
                        "url": request.url,
                        "method": request.method,
                        "headers": request.headers,
                        "post_data": request.post_data
                    }
                    api_endpoints_found.append(entry)
                    print(f"\n[REQ] {request.method} {request.url}")
                    if request.post_data:
                        try:
                            # Try print nicely if JSON
                            parsed = json.loads(request.post_data)
                            print("        Payload:", json.dumps(parsed, ensure_ascii=False)[:200], "...")
                        except:
                            print("        Payload:", request.post_data[:200])

        def handle_response(response):
            """Log responses for matching requests"""
            url = response.url.lower()
            if "api" in url or "graphql" in url or "indicator" in url or "srem" in url:
                if response.request.resource_type in ["fetch", "xhr"]:
                    try:
                        content_type = response.headers.get("content-type", "")
                        print(f"[RES] {response.status} | {content_type}")
                    except Exception:
                        pass

        page.on("request", handle_request)
        page.on("response", handle_response)
        
        # 1. Navigating to the index
        print("Navigating to https://srem.moj.gov.sa/ ...")
        
        try:
            # We use wait_until="domcontentloaded" to not block on tracking pixels
            page.goto("https://srem.moj.gov.sa/", timeout=25000, wait_until="domcontentloaded")
            print("Page Initialized. Waiting 8 seconds for background API calls to settle...")
            page.wait_for_timeout(8000)
            
            # Find and dump the collected APIs
            print("\n================ FINAL API DUMP ================")
            with open("moj_apis_dump.json", "w", encoding="utf-8") as f:
                json.dump(api_endpoints_found, f, indent=4, ensure_ascii=False)
            print(f"Dumped {len(api_endpoints_found)} API requests to 'moj_apis_dump.json'.")
            
        except Exception as e:
            print(f"Failed to navigate or timeout: {e}")
            
        browser.close()

if __name__ == "__main__":
    run()
