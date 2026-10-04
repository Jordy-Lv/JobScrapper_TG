#!/usr/bin/env python3
import re, json, subprocess, sys, os

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def http(url):
    try:
        r = subprocess.run(["curl","-s","-A",UA,"--max-time","40",url], capture_output=True, text=True)
        return r.stdout
    except Exception as e:
        print("ERR", e, file=sys.stderr)
        return ""

def parse_linkedin(html):
    jobs = []
    # Split on base-card
    cards = re.split(r'<div class="base-search-card', html)
    for card in cards[1:]:
        urn = re.search(r'urn:li:jobPosting:(\d+)', card)
        if not urn: continue
        jid = urn.group(1)
        title_m = re.search(r'<span class="sr-only">\s*(.*?)\s*</span>', card, re.S)
        title = re.sub(r'\s+',' ',title_m.group(1)).strip() if title_m else ""
        comp = re.search(r'base-search-card__subtitle[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>', card, re.S)
        company = re.sub(r'\s+',' ',comp.group(1)).strip() if comp else ""
        loc = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', card, re.S)
        location = re.sub(r'\s+',' ',loc.group(1)).strip() if loc else ""
        date = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', card)
        dt = date.group(1) if date else ""
        link = f"https://www.linkedin.com/jobs/view/{jid}"
        jobs.append({"id":jid,"title":title,"company":company,"location":location,"date":dt,"url":link})
    return jobs

queries = [
    ("aprendiz_remoto_desarrollo","https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=aprendiz+remoto+desarrollo&location=Colombia&f_WT=2&f_TPR=r604800&start=0&count=25"),
    ("practicante_remoto_software","https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=practicante+remoto+software&location=Colombia&f_WT=2&f_TPR=r604800&start=0&count=25"),
    ("aprendiz_hibrido_desarrollo","https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=aprendiz+hibrido+desarrollo&location=Colombia&f_WT=3&f_TPR=r604800&start=0&count=25"),
    ("practicante_hibrido_sistemas","https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=practicante+hibrido+sistemas&location=Colombia&f_WT=3&f_TPR=r604800&start=0&count=25"),
    ("practicante_presencial_cartagena","https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=practicante+presencial+cartagena+sistemas&location=Colombia&f_WT=1&f_TPR=r604800&start=0&count=25"),
    ("aprendiz_presencial_cartagena","https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=aprendiz+presencial+cartagena+desarrollo&location=Colombia&f_WT=1&f_TPR=r604800&start=0&count=25"),
]

alljobs = []
for name, url in queries:
    html = http(url)
    jobs = parse_linkedin(html)
    for j in jobs:
        j["fuente"] = name
        alljobs.append(j)

# dedupe by id
seen=set(); out=[]
for j in alljobs:
    if j["id"] not in seen:
        seen.add(j["id"]); out.append(j)

for j in out:
    print(f'{j["id"]}\t{j["date"]}\t{j["company"]}\t{j["title"]}\t{j["location"]}\t{j["url"]}\t{j["fuente"]}')
