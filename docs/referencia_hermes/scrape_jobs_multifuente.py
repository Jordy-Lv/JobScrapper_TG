#!/usr/bin/env python3
import json, re, subprocess, sys, html as html_mod

results = []

# ====== 1. EL EMPLEO ======
try:
    html = subprocess.check_output([
        "curl", "-s", "-L", "-H", "User-Agent: Mozilla/5.0",
        "https://www.elempleo.com/co/ofertas-empleo/?busqueda=desarrollador+junior&modalidad=remoto&pagina=1"
    ], timeout=30).decode("utf-8", errors="replace")

    # Find all JSON-LD blocks
    jsonld_pattern = r'<script type="application/ld\+json"[^>]*>(.*?)</script>'
    scripts = re.findall(jsonld_pattern, html, re.DOTALL)
    
    ee_count = 0
    for script in scripts:
        try:
            data = json.loads(script)
            if not isinstance(data, dict):
                continue
            # Only process ItemList type
            if data.get("@type") != "ItemList":
                continue
            item_list = data.get("itemListElement")
            if item_list and isinstance(item_list, list):
                for item in item_list:
                    item_data = item.get("item", {})
                    url = item_data.get("@id", "")
                    name = item_data.get("name", "")
                    if url and name:
                        results.append({
                            "fuente": "ElEmpleo",
                            "cargo": html_mod.unescape(name.strip()),
                            "empresa": "",
                            "url": url,
                            "raw_job_id": f"ee-{item.get('position', ee_count+1)}",
                            "tags": "",
                            "ciudad": "Remoto"
                        })
                        ee_count += 1
        except json.JSONDecodeError:
            continue
    
    print(f"[OK] El Empleo: {ee_count} jobs extracted", file=sys.stderr)
except Exception as e:
    print(f"[SKIP] El Empleo: {e}", file=sys.stderr)

# ====== 2. MAGNETO EMPLEOS ======
# Skipped - confirmed empty response

# ====== 3. REMOTEOK ======
try:
    raw = subprocess.check_output([
        "curl", "-s", "https://remoteok.com/api"
    ], timeout=30).decode("utf-8", errors="replace")
    data = json.loads(raw)
    filter_keywords = ["junior", "java", "react", "full stack", "fullstack", "backend", "frontend", "front end", "dev", "developer", "spring", "angular", "vue", "node", "javascript", "typescript", "python", "golang", "engineering", "engineer", "software"]
    filtered = 0
    total_with_tags = 0
    for j in data:
        if not isinstance(j, dict):
            continue
        tags = j.get("tags", [])
        if not tags:
            continue
        total_with_tags += 1
        tags_lower = [t.lower() for t in tags]
        tags_str = ",".join(tags)
        matched = False
        for kw in filter_keywords:
            kw_lower = kw.lower()
            for t in tags_lower:
                if kw_lower in t:
                    matched = True
                    break
            if matched:
                break
        if matched:
            filtered += 1
            results.append({
                "fuente": "RemoteOK",
                "cargo": j.get("position", ""),
                "empresa": j.get("company", ""),
                "url": j.get("url", ""),
                "raw_job_id": f"rok-{j.get('id', '')}",
                "tags": tags_str,
                "ciudad": j.get("location", "")
            })
    print(f"[OK] RemoteOK: {filtered} jobs matched filter out of {total_with_tags} with tags", file=sys.stderr)
except Exception as e:
    print(f"[SKIP] RemoteOK: {e}", file=sys.stderr)

# ====== 4. GET ON BOARD ======
try:
    raw = subprocess.check_output([
        "curl", "-s", "https://www.getonbrd.com/api/v0/search/jobs?query=junior+java+spring&per_page=20"
    ], timeout=30).decode("utf-8", errors="replace")
    gob_data = json.loads(raw)
    jobs = gob_data.get("data", [])
    for j in jobs:
        attrs = j.get("attributes", {})
        # Company name - try direct field first, then relationships
        company = attrs.get("company", "")
        if not company or not isinstance(company, str):
            company = ""
        
        # URL
        apply_url = attrs.get("apply_url", "")
        public_url = j.get("links", {}).get("public_url", "")
        attr_url = attrs.get("url", "")
        url = ""
        if apply_url and isinstance(apply_url, str):
            if apply_url.startswith("http"):
                url = apply_url
            else:
                url = "https://www.getonbrd.com" + apply_url
        elif public_url and isinstance(public_url, str):
            url = public_url
        elif attr_url and isinstance(attr_url, str):
            url = attr_url
        
        # Modality / city
        modality = attrs.get("modality", "")
        if not modality or not isinstance(modality, str):
            modality = attrs.get("remote_modality", "") or ""
        if not isinstance(modality, str):
            modality = ""
            
        # For the specific result we saw, also check the location
        location_cities = attrs.get("location_cities", {})
        
        results.append({
            "fuente": "GetOnBoard",
            "cargo": attrs.get("title", ""),
            "empresa": company,
            "url": url,
            "raw_job_id": f"gob-{j.get('id', '')}",
            "tags": "",
            "ciudad": modality
        })
    print(f"[OK] GetOnBoard: {len(jobs)} jobs", file=sys.stderr)
except Exception as e:
    print(f"[SKIP] GetOnBoard: {e}", file=sys.stderr)

# ====== OUTPUT ======
print(json.dumps(results, ensure_ascii=False, indent=2))
print(f"\n--- TOTAL: {len(results)} jobs ---", file=sys.stderr)
