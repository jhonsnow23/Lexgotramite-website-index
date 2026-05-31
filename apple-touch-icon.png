import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE_FILE = os.path.join(ROOT, "publish_state.json")

def env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value

def get_access_token():
    payload = urllib.parse.urlencode({
        "client_id": env("GSC_CLIENT_ID"),
        "client_secret": env("GSC_CLIENT_SECRET"),
        "refresh_token": env("GSC_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=payload, method="POST")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return data["access_token"]

def auth_headers(token, json_body=False):
    headers = {"Authorization": f"Bearer {token}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers

def submit_sitemap(token):
    site_url = urllib.parse.quote(env("GSC_SITE_URL"), safe="")
    sitemap_url = urllib.parse.quote(env("GSC_SITEMAP_URL"), safe=":/")
    endpoint = f"https://www.googleapis.com/webmasters/v3/sites/{site_url}/sitemaps/{sitemap_url}"
    req = urllib.request.Request(endpoint, headers=auth_headers(token), method="PUT")
    with urllib.request.urlopen(req) as resp:
        return resp.status

def load_last_published_url():
    if not os.path.exists(STATE_FILE):
        return None
    state = json.loads(open(STATE_FILE, encoding="utf-8").read())
    last_published = state.get("last_published") or {}
    return last_published.get("url")

def inspect_url(token, url):
    site_url = env("GSC_SITE_URL")
    payload = json.dumps({"inspectionUrl": url, "siteUrl": site_url}).encode()
    req = urllib.request.Request(
        "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
        data=payload,
        headers=auth_headers(token, json_body=True),
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def main():
    token = get_access_token()
    submit_status = submit_sitemap(token)
    print(f"Sitemap enviada/actualizada en Search Console (HTTP {submit_status}).")

    url = load_last_published_url()
    if not url:
        print("No hay último artículo publicado; se omite la inspección de URL.")
        return

    result = inspect_url(token, url)
    output_path = os.path.join(ROOT, "search_console_last_inspection.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Inspección guardada en {output_path} para {url}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error en automatización de Search Console: {exc}", file=sys.stderr)
        sys.exit(1)
