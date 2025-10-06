# scraper.py
import os, json, time, smtplib, ssl, re, xml.etree.ElementTree as ET
from email.message import EmailMessage
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jobs.json")

# ---- Targets: your Seek URL + Indeed RSS ----
TARGETS = [
    {
        "name": "Seek – Bendigo ICT (100km, newest)",
        "type": "seek",
        "url": "https://www.seek.com.au/jobs-in-information-communication-technology/in-Bendigo-VIC-3550?distance=100&sortmode=ListedDate",
        "item": 'article[data-automation="normalJob"], article[data-automation="jobCard"]',
        "fields": {
            "title": 'a[data-automation="jobTitle"]',
            "company": '[data-automation="jobCompany"]',
            "location": '[data-automation="jobLocation"]',
            "link": 'a[data-automation="jobTitle"][href]'
        }
    },
    {
        "name": "Indeed RSS – Bendigo ICT",
        "type": "indeed_rss",
        "url": "https://au.indeed.com/rss?q=information+technology&l=Bendigo+VIC&radius=100&sort=date"
    }
]

# ---- Helpers ----
def extract_text(node, css):
    if not css: return None
    el = node.select_one(css.split("[")[0])
    return el.get_text(strip=True) if el else None

def extract_attr(node, css, attr="href"):
    if not css: return None
    el = node.select_one(css)
    return el.get(attr) if el and el.has_attr(attr) else None

def parse_seek_jsonld(html):
    # Fallback: collect JobPosting objects from embedded JSON-LD
    items = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, flags=re.I|re.S
    ):
        try:
            data = json.loads(m.group(1))
            arr = data if isinstance(data, list) else [data]
            for obj in arr:
                if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                    title = obj.get("title")
                    company = (obj.get("hiringOrganization") or {}).get("name")
                    loc = None
                    jl = obj.get("jobLocation")
                    if isinstance(jl, list) and jl:
                        loc = (jl[0].get("address") or {}).get("addressLocality")
                    elif isinstance(jl, dict):
                        loc = (jl.get("address") or {}).get("addressLocality")
                    url = obj.get("hiringOrganization", {}).get("sameAs") or obj.get("url")
                    items.append({
                        "source": "Seek – JSON-LD",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "link": url
                    })
        except Exception:
            continue
    return items

def parse_indeed_rss(xml_text):
    # Minimal RSS parser: "Job Title - Company"
    out = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        jt, comp = None, None
        if " - " in title:
            jt, comp = title.split(" - ", 1)
        else:
            jt = title
        out.append({
            "source": "Indeed RSS",
            "title": jt or None,
            "company": comp or None,
            "location": None,
            "link": link or None
        })
    return out

def scrape():
    headers = {"User-Agent": "JobScout/1.0 (+github.com/quanghungthai)"}
    out = []
    for site in TARGETS:
        try:
            if site["type"] == "indeed_rss":
                xml = requests.get(site["url"], headers=headers, timeout=20).text
                out.extend(parse_indeed_rss(xml))
                time.sleep(1)
                continue

            # default: Seek HTML, then JSON-LD fallback
            html = requests.get(site["url"], headers=headers, timeout=20).text
            if site["type"] == "seek":
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select(site["item"])
                if cards:
                    for node in cards:
                        rec = {
                            "source": site["name"],
                            "title": extract_text(node, site["fields"]["title"]),
                            "company": extract_text(node, site["fields"]["company"]),
                            "location": extract_text(node, site["fields"]["location"]),
                            "link": extract_attr(node, site["fields"]["link"]) or None
                        }
                        if any(rec.values()):
                            out.append(rec)
                else:
                    out.extend(parse_seek_jsonld(html))

            time.sleep(1)  # be polite
        except Exception as e:
            out.append({"source": site["name"], "title": f"[ERROR] {e}", "company": None, "location": None, "link": site.get("url")})
    return out

def write_json(items):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return OUTPUT_FILE

def maybe_email(attachment_path):
    host = os.getenv("SMTP_SERVER")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USERNAME")
    pwd  = os.getenv("SMTP_PASSWORD")
    to   = os.getenv("TO_EMAIL")
    frm  = os.getenv("FROM_EMAIL", user)

    if not all([host, port, user, pwd, to, frm]):
        print("Email env vars not set; skipping email.")
        return

    msg = EmailMessage()
    msg["Subject"] = "Job scrape results"
    msg["From"] = frm
    msg["To"] = to
    msg.set_content("Attached: jobs.json")

    with open(attachment_path, "rb") as f:
        data = f.read()
    msg.add_attachment(data, maintype="application", subtype="json", filename="jobs.json")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        server.login(user, pwd)
        server.send_message(msg)
    print("Email sent.")

if __name__ == "__main__":
    items = scrape()
    path = write_json(items)
    print(f"Wrote {path} with {len(items)} records.")
    maybe_email(path)
