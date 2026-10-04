#!/usr/bin/env python3
"""Scrape El Empleo Colombia for junior dev jobs."""
import json
import re

with open('/tmp/elempleo.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Pattern to match each job listing's wrapper div
pattern = re.compile(
    r'class="col-md-12 p-0 js-area-bind area-bind" '
    r'data-url="(?P<url>[^"]*)" '
    r'data-ga4-offerdata="(?P<ga4>[^"]*)"',
    re.DOTALL
)

base_url = "https://www.elempleo.com"

jobs = []
for match in pattern.finditer(html):
    # Parse the HTML-escaped JSON in data-ga4-offerdata
    ga4_raw = match.group('ga4')
    # Unescape HTML entities
    ga4_json = ga4_raw.replace('&quot;', '"').replace('&#225;', 'á').replace('&#243;', 'ó').replace('&#237;', 'í').replace('&#233;', 'é').replace('&#241;', 'ñ').replace('&#250;', 'ú')
    try:
        ga4 = json.loads(ga4_json)
    except json.JSONDecodeError:
        continue

    job_id = ga4.get('id')
    title = ga4.get('title', '')
    company = ga4.get('company', '')
    city = ga4.get('location', '')
    path = match.group('url')
    full_url = base_url + path if path else ''

    # Normalize HTML entities in city
    city = city.replace('&#225;', 'á').replace('&#243;', 'ó').replace('&#237;', 'í').replace('&#233;', 'é').replace('&#241;', 'ñ').replace('&#250;', 'ú')

    jobs.append({
        "id": job_id,
        "fuente": "El Empleo Colombia",
        "cargo": title,
        "empresa": company,
        "ciudad": city,
        "url": full_url
    })

output = json.dumps(jobs, ensure_ascii=False, indent=2)
print(output)

# Also write to file
with open('/home/ByLOGAN/elempleo_junior_jobs.json', 'w', encoding='utf-8') as f:
    f.write(output)

print(f"\n--- Found {len(jobs)} job listings ---")
