#!/usr/bin/env python3
"""Job scraper - busca vacantes junior de desarrollo de software en Colombia"""
import json, re, subprocess, os, sys
from datetime import datetime

HISTORY_FILE = os.path.expanduser("~/.hermes/cron/output/historial_vacantes.json")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        return data.get("vacantes", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(vacantes):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump({"vacantes": vacantes}, f, indent=2)

history = load_history()
print(f"📋 Historial cargado: {len(history)} vacantes previas")

known_ids = set()
for v in history:
    rid = v.get("raw_job_id", "")
    if rid:
        known_ids.add(rid)
    url = v.get("url", "")
    m = re.search(r'(\d{6,})', url)
    if m:
        known_ids.add(m.group(1))
    emp = v.get("empresa", v.get("company", "")).strip().lower()
    car = v.get("cargo", "").strip().lower()
    if emp and car:
        known_ids.add(f"key:{emp}|{car}")

print(f"🔑 IDs conocidos: {len(known_ids)}")

def curl_fetch(url, timeout=25):
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "-m", str(timeout),
             "-H", f"User-Agent: {USER_AGENT}",
             "-H", "Accept: text/html,application/xhtml+xml,application/json",
             url],
            capture_output=True, text=True, timeout=timeout+5
        )
        return result.stdout, result.returncode
    except Exception as e:
        return f"ERROR: {e}", -1

def parse_linkedin_jobs(html, fuente_label):
    jobs = []
    seen_ids = set()
    for m in re.finditer(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html):
        job_id = m.group(1)
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)
        pos = m.start()
        chunk = html[max(0,pos-200):pos+3000]
        
        title_m = re.search(r'base-search-card__title[^>]*>\s*(.*?)\s*</h3>', chunk, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "N/A"
        
        sub_m = re.search(r'base-search-card__subtitle[^>]*>.*?<a[^>]*>(.*?)</a>', chunk, re.DOTALL)
        company = re.sub(r'<[^>]+>', '', sub_m.group(1)).strip() if sub_m else "N/A"
        
        loc_m = re.search(r'job-search-card__location[^>]*>\s*(.*?)\s*</span>', chunk, re.DOTALL)
        location = loc_m.group(1).strip() if loc_m else "N/A"
        
        date_m = re.search(r'<time[^>]*datetime="([^"]*)"', chunk)
        date_str = date_m.group(1) if date_m else ""
        
        href_m = re.search(r'href="(https?://[^"]*' + job_id + r'[^"]*)"', chunk)
        url = ""
        if href_m:
            url = href_m.group(1).split("?")[0].replace("&amp;", "&")
        else:
            url = f"https://co.linkedin.com/jobs/view/{job_id}"
        
        jobs.append({
            "cargo": title, "empresa": company, "ciudad": location,
            "fecha": date_str, "url": url, "raw_job_id": job_id,
            "fuente": fuente_label
        })
    return jobs

def parse_computrabajo(html, fuente_label):
    jobs = []
    # Extract links, strip # fragment
    links = re.findall(r'href="(/ofertas-de-trabajo/[^"]+)"', html, re.IGNORECASE)
    seen = set()
    for link in links:
        # Strip fragment
        clean_link = link.split('#')[0]
        # Skip non-job links (empresas pages)
        if 'empresas/ofertas' in clean_link:
            continue
        # Extract hash ID from end
        id_m = re.search(r'([A-F0-9]{32})$', clean_link, re.IGNORECASE)
        raw_id = id_m.group(1) if id_m else clean_link
        if raw_id in seen:
            continue
        seen.add(raw_id)
        url_lower = clean_link.lower()
        cargo_m = re.search(r'/oferta-de-trabajo-de-(.+?)-en-', url_lower)
        cargo = cargo_m.group(1).replace("-", " ").title() if cargo_m else "N/A"
        ciudad_m = re.search(r'-en-([a-z-]+)-[a-f0-9]', url_lower)
        ciudad = ciudad_m.group(1).replace("-", " ").title() if ciudad_m else "N/A"
        # Clean up ciudad - remove trailing hash remnants
        if ciudad and '#' in ciudad:
            ciudad = ciudad.split('#')[0]
        jobs.append({
            "cargo": cargo, "empresa": "Por determinar", "ciudad": ciudad,
            "fecha": "", "url": "https://www.computrabajo.com.co" + clean_link,
            "raw_job_id": raw_id, "fuente": fuente_label
        })
    return jobs

def parse_remoteok(html):
    jobs = []
    try:
        data = json.loads(html)
        if isinstance(data, list):
            for item in data[:30]:
                if not isinstance(item, dict) or "id" not in item:
                    continue
                title = item.get("position", "")
                tags = [t.lower() for t in item.get("tags", [])]
                title_lower = title.lower()
                # MUST be software development related
                dev_keywords = ["java", "react", "full stack", "fullstack", "backend", "frontend",
                               "software engineer", "developer", "software", "engineer",
                               "web developer", "programmer", "coding", "code", "api",
                               "javascript", "typescript", "node", "python", "spring",
                               "docker", "kubernetes", "devops", "data engineer",
                               "full-stack", "react native", "mobile developer"]
                if not any(kw in title_lower for kw in dev_keywords):
                    continue
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = "https://remoteok.com" + url
                jobs.append({
                    "cargo": title, "empresa": item.get("company", ""),
                    "ciudad": "Remoto", "fecha": item.get("date", ""),
                    "url": url, "raw_job_id": f"remoteok-{item.get('id', '')}",
                    "fuente": "RemoteOK"
                })
    except json.JSONDecodeError:
        pass
    return jobs

def parse_getonboard(html):
    jobs = []
    try:
        data = json.loads(html)
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            title = attrs.get("title", "")
            company = attrs.get("company", {}).get("name", "") if isinstance(attrs.get("company"), dict) else ""
            slug = attrs.get('slug', '')
            url = f"https://www.getonbrd.com/jobs/{slug}" if slug else ""
            remote = attrs.get("remote", False)
            location = "Remoto/LATAM" if remote else "LATAM"
            jobs.append({
                "cargo": title, "empresa": company, "ciudad": location,
                "fecha": attrs.get("published_at", ""), "url": url,
                "raw_job_id": f"gob-{slug or item.get('id', '')}",
                "fuente": "Get On Board"
            })
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return jobs

def is_new_job(job):
    rid = job.get("raw_job_id", "")
    if rid and rid in known_ids:
        return False
    url = job.get("url", "")
    m = re.search(r'(\d{6,})', url)
    if m and m.group(1) in known_ids:
        return False
    emp = job.get("empresa", "").strip().lower()
    car = job.get("cargo", "").strip().lower()
    if emp and car and f"key:{emp}|{car}" in known_ids:
        return False
    return True

def filter_job(job):
    cargo = job.get("cargo", "").lower()
    ciudad = job.get("ciudad", "").lower()
    empresa = job.get("empresa", "").lower()
    
    combined = f"{cargo} {ciudad} {empresa}"
    
    # EXCLUDE: non-software roles
    exclude_terms = [
        "fisioterapia", "docente", "profesor", "teacher", "physiotherapy",
        "recursos humanos", "administrativa", "talento humano",
        "alimentos", "food technology", "sell out", "gestor",
        "mercadeo", "marketing", "commercial", "administrative assistant",
        "data entry", "typist", "clerk", "admin assistant",
        "asistente administrativo", "asistente virtual",
        "ejecutivo", "ventas", "sales", "call center", "atención al cliente",
        "customer service", "cocinero", "chef", "enfermer", "medico",
        "conductor", "chofer", "vigilante", "seguridad",
        "comercial", "logistica", "logística", "producción",
        "contador", "contable", "financiero", "finanzas",
        "diseñador grafico", "graphic design", "community manager",
        "operario", "operador", "técnico electricista", "mecánico",
        "albañil", "construcción", "servicios generales",
        "inteligencia de negocios", "business intelligence",
        "food", "aliment", "nutricion", "nutrición"
    ]
    for term in exclude_terms:
        if term in combined:
            return False
    
    # EXCLUDE senior/semisenior
    if re.search(r'\b(senior|staff\s|principal|architect|lead\s|manager|director|head\s|semisenior|semi.senior|semi senior)\b', cargo):
        return False
    
    # INCLUDE only software development roles
    dev_keywords = [
        "java", "spring", "react", "javascript", "typescript", "html", "css",
        "backend", "frontend", "full stack", "fullstack", "full-stack",
        "developer", "desarrollador", "programador", "software engineer",
        "software developer", "ingenier", "web developer", "web dev",
        "practicante", "aprendiz", "trainee", "junior", "entry level",
        "intern", "estudiante", "sin experiencia", "api", "rest",
        "mysql", "postgresql", "docker", "git", "github", "node", "angular",
        ".net", "python", "sistemas", "desarrollo de software",
        "integration developer", "jvm", "mobile developer",
        "full-stack engineer", "front-end", "back-end", "back end",
        "data engineer", "codigo", "código", "desarrollo de aplicaciones",
        "bases de datos", "programador web", "programadora web",
        "analista de desarrollo", "analista programador",
        "apprentice", "practicing", "programa de practicantes",
        "apx", "aso", "cells", "soporte ti desarrollo",
        "convocatoria practicantes", "software craftsperson"
    ]
    if not any(kw in cargo for kw in dev_keywords):
        return False
    
    # LOCATION: skip presencial roles NOT in Cartagena
    presencial_cities = ["bogota", "bogotá", "medellin", "medellín", "cali", "barranquilla",
                         "pereira", "manizales", "bucaramanga", "ibague", "ibagué",
                         "villavicencio", "neiva", "sincelejo", "monteria", "montería",
                         "pasto", "armenia", "cucuta", "cúcuta", "seville", "sevilla"]
    is_remote = any(kw in ciudad for kw in ["remoto", "remote", "home", "virtual", "online", "latam"])
    is_colombia = any(kw in ciudad for kw in ["colombia"])
    is_cartagena = "cartagena" in ciudad
    
    if not is_remote and not is_colombia and not is_cartagena:
        for city in presencial_cities:
            if city in ciudad:
                return False
    
    return True

def calculate_priority(job):
    cargo = job.get("cargo", "").lower()
    ciudad = job.get("ciudad", "").lower()
    score = 0
    
    if "remoto" in ciudad or any(kw in ciudad for kw in ["colombia", "latam", "remote"]):
        score += 30
    if "cartagena" in ciudad:
        score += 20
    if "java" in cargo and "spring" in cargo:
        score += 25
    elif "java" in cargo:
        score += 15
    if "spring" in cargo and "java" not in cargo:
        score += 10
    if "backend" in cargo or "back-end" in cargo or "back end" in cargo:
        score += 15
    if "full stack" in cargo or "fullstack" in cargo or "full-stack" in cargo:
        score += 12
    if "react" in cargo:
        score += 8
    if "frontend" in cargo or "front-end" in cargo or "front end" in cargo:
        score += 5
    if any(kw in cargo for kw in ["junior", "entry", "trainee", "sin experiencia", "aprendiz", "practicante"]):
        score += 10
    if "aprendiz" in cargo:
        score += 5
    if "integration" in cargo and "java" in cargo:
        score += 20
    if "python" in cargo:
        score += 5
    
    return min(score, 100)

# ====== MAIN ======
all_new_jobs = []

linkedin_queries = [
    ("java+junior", "Colombia", "f_WT=2&f_TPR=r259200", 20, "LinkedIn (java+junior)"),
    ("spring+boot+junior", "Colombia", "f_WT=2&f_TPR=r259200", 20, "LinkedIn (spring+boot)"),
    ("junior+desarrollador", "Cartagena", "f_TPR=r259200", 15, "LinkedIn (Cartagena)"),
    ("entry+level+software+developer", "Colombia", "f_TPR=r259200", 20, "LinkedIn (entry+level)"),
    ("aprendiz+desarrollo+software", "Colombia", "f_TPR=r259200", 15, "LinkedIn (aprendiz)"),
    ("practicante+desarrollo", "Colombia", "f_TPR=r259200", 15, "LinkedIn (practicante)"),
    ("junior+frontend+react", "Colombia", "f_WT=2&f_TPR=r259200", 15, "LinkedIn (frontend+react)"),
    ("full+stack+junior", "Colombia", "f_WT=2&f_TPR=r259200", 15, "LinkedIn (full+stack)"),
    ("junior+backend", "Colombia", "f_WT=2&f_TPR=r259200", 15, "LinkedIn (junior+backend)"),
    ("sin+experiencia+desarrollador", "Colombia", "f_TPR=r259200", 15, "LinkedIn (sin+experiencia)"),
    ("trainee+java", "Colombia", "f_TPR=r259200", 15, "LinkedIn (trainee+java)"),
]

print("\n🔍 LinkedIn...")
for keywords, location, extra, count, label in linkedin_queries:
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location={location}&{extra}&start=0&count={count}"
    html, code = curl_fetch(url)
    if code == 0 and html and "ERROR" not in html[:20]:
        jobs = parse_linkedin_jobs(html, label)
        for j in jobs:
            j["fecha_descubrimiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if is_new_job(j) and filter_job(j):
                j["prioridad"] = calculate_priority(j)
                j["es_prioritaria"] = j["prioridad"] >= 60
                all_new_jobs.append(j)
        matched = sum(1 for j in jobs if is_new_job(j) and filter_job(j))
        print(f"  {label}: {len(jobs)} jobs, {matched} new {'✓' if matched else ''}")
    else:
        print(f"  {label}: Error/bloqueo")

computrabajo_slugs = [
    ("desarrollador-junior", "Computrabajo (junior)"),
    ("aprendiz-desarrollo-de-software", "Computrabajo (aprendiz)"),
    ("practicante-desarrollo", "Computrabajo (practicante)"),
    ("java-junior", "Computrabajo (java)"),
    ("programador-junior", "Computrabajo (programador)"),
    ("full-stack-junior", "Computrabajo (fullstack)"),
]
print("\n🔍 Computrabajo...")
for slug, label in computrabajo_slugs:
    url = f"https://www.computrabajo.com.co/trabajo-de-{slug}?pubdate=3"
    html, code = curl_fetch(url)
    if code == 0 and html and "ERROR" not in html[:20]:
        jobs = parse_computrabajo(html, label)
        for j in jobs:
            j["fecha_descubrimiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if is_new_job(j) and filter_job(j):
                j["prioridad"] = calculate_priority(j)
                j["es_prioritaria"] = j["prioridad"] >= 60
                all_new_jobs.append(j)
        matched = sum(1 for j in jobs if is_new_job(j) and filter_job(j))
        print(f"  {label}: {len(jobs)} jobs, {matched} new {'✓' if matched else ''}")
    else:
        print(f"  {label}: Error/bloqueo")

print("\n🔍 El Empleo...")
url = "https://www.elempleo.com/co/ofertas-empleo/?busqueda=desarrollador+junior&modalidad=remoto&pagina=1"
html, code = curl_fetch(url)
if code == 0 and html:
    # Find job cards
    cards = re.findall(r'<div[^>]*class="[^"]*result-item[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>', html, re.DOTALL)
    if not cards:
        # Fallback: look for titles and links
        titles = re.findall(r'class="[^"]*js-offer-title[^"]*"[^>]*>(.*?)<', html, re.DOTALL)
        companies = re.findall(r'class="[^"]*js-offer-company[^"]*"[^>]*>(.*?)<', html, re.DOTALL)
        cities = re.findall(r'class="[^"]*info-city[^"]*"[^>]*>(.*?)<', html, re.DOTALL)
        links = re.findall(r'href="(https?://[^"]*ofertas[^"]*)"', html)
        
        titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles]
        companies = [re.sub(r'<[^>]+>', '', c).strip() for c in companies]
        cities = [re.sub(r'<[^>]+>', '', c).strip() for c in cities]
        
        for i, title in enumerate(titles[:20]):
            url_job = links[i] if i < len(links) else ""
            id_m = re.search(r'(\d{8,})', url_job) if url_job else None
            raw_id = id_m.group(1) if id_m else f"elempleo-{i}"
            company = companies[i] if i < len(companies) else "Por determinar"
            city = cities[i] if i < len(cities) else "Colombia"
            
            job = {"cargo": title, "empresa": company, "ciudad": city,
                   "fecha": "", "url": url_job.split("?")[0] if url_job else "",
                   "raw_job_id": f"elempleo-{raw_id}", "fuente": "El Empleo",
                   "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            if is_new_job(job) and filter_job(job):
                job["prioridad"] = calculate_priority(job)
                job["es_prioritaria"] = job["prioridad"] >= 60
                all_new_jobs.append(job)
        print(f"  {len(titles)} títulos encontrados")
    else:
        print(f"  {len(cards)} cards encontrados")
else:
    print(f"  Error/bloqueo")

print("\n🔍 RemoteOK...")
url = "https://remoteok.com/api"
html, code = curl_fetch(url)
if code == 0 and html:
    jobs = parse_remoteok(html)
    for j in jobs:
        j["fecha_descubrimiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if is_new_job(j) and filter_job(j):
            j["prioridad"] = calculate_priority(j)
            j["es_prioritaria"] = j["prioridad"] >= 60
            all_new_jobs.append(j)
    matched = sum(1 for j in jobs if is_new_job(j) and filter_job(j))
    print(f"  {len(jobs)} relevantes, {matched} new {'✓' if matched else ''}")
else:
    print(f"  Error/bloqueo")

print("\n🔍 Magneto...")
url = "https://www.magnetoempleos.com.co/busqueda/?q=desarrollador+junior+remoto&page=1"
html, code = curl_fetch(url)
if code == 0 and html:
    links = re.findall(r'href="(/empleo/[^"]+)"', html)
    titles = [re.sub(r'<[^>]+>', '', t).strip() for t in re.findall(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL)]
    for i, link in enumerate(links[:20]):
        full_url = "https://www.magnetoempleos.com.co" + link
        id_m = re.search(r'(\d+)', link)
        raw_id = id_m.group(1) if id_m else f"magneto-{i}"
        title = titles[i] if i < len(titles) else "N/A"
        job = {"cargo": title, "empresa": "Por determinar", "ciudad": "Colombia",
               "fecha": "", "url": full_url,
               "raw_job_id": f"magneto-{raw_id}", "fuente": "Magneto",
               "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if is_new_job(job) and filter_job(job):
            job["prioridad"] = calculate_priority(job)
            job["es_prioritaria"] = job["prioridad"] >= 60
            all_new_jobs.append(job)
    print(f"  {len(links)} enlaces encontrados")
else:
    print(f"  Error/bloqueo")

print("\n🔍 Get On Board...")
url = "https://www.getonbrd.com/api/v0/search/jobs?query=junior+java+spring&per_page=20"
html, code = curl_fetch(url)
if code == 0 and html:
    jobs = parse_getonboard(html)
    for j in jobs:
        j["fecha_descubrimiento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if is_new_job(j) and filter_job(j):
            j["prioridad"] = calculate_priority(j)
            j["es_prioritaria"] = j["prioridad"] >= 60
            all_new_jobs.append(j)
    matched = sum(1 for j in jobs if is_new_job(j) and filter_job(j))
    print(f"  {len(jobs)} relevantes, {matched} new {'✓' if matched else ''}")
else:
    print(f"  Error/bloqueo")

# Dedup
print(f"\n🧹 Total nuevas en bruto: {len(all_new_jobs)}")
seen_ids = set()
deduped = []
for j in all_new_jobs:
    key = j.get("raw_job_id", "") or j.get("url", "").lower()
    if key and key not in seen_ids:
        seen_ids.add(key)
        deduped.append(j)
print(f"🧹 Después de dedup: {len(deduped)}")

deduped.sort(key=lambda j: -j.get("prioridad", 0))

for j in deduped:
    history.append(j)
save_history(history)
print(f"💾 Historial guardado: {len(history)} vacantes")

# ====== OUTPUT ======
if not deduped:
    print("\n🔄 Búsqueda completada - Sin vacantes nuevas que reportar.")
else:
    print(f"\n✅ {len(deduped)} VACANTES NUEVAS ENCONTRADAS\n")
    
    for job in deduped:
        prioridad = job.get("prioridad", 0)
        cargo = job.get("cargo", "N/A")
        empresa = job.get("empresa", "N/A")
        ciudad = job.get("ciudad", "N/A")
        url = job.get("url", "N/A")
        fuente = job.get("fuente", "N/A")
        fecha = job.get("fecha", "")
        
        if prioridad >= 80: stars = "⭐⭐⭐⭐⭐"
        elif prioridad >= 60: stars = "⭐⭐⭐⭐"
        elif prioridad >= 40: stars = "⭐⭐⭐"
        elif prioridad >= 20: stars = "⭐⭐"
        else: stars = "⭐"
        
        print(f"\n{'='*60}")
        if job.get("es_prioritaria"):
            print(f"🚀 {stars} OPORTUNIDAD PRIORITARIA 🚀")
        else:
            print(f"  {stars} OPORTUNIDAD")
        
        print(f"📌 Cargo: {cargo}")
        print(f"🏢 Empresa: {empresa}")
        print(f"📍 Ciudad: {ciudad}")
        
        modalidad = "Remoto" if any(kw in ciudad.lower() for kw in ["remoto", "remote", "home", "latam"]) else "Por determinar"
        if "remoto" in cargo.lower() or "remote" in cargo.lower():
            modalidad = "Remoto"
        print(f"💻 Modalidad: {modalidad}")
        print(f"⏳ Experiencia: Junior / Entry Level")
        print(f"📅 Fecha: {fecha if fecha else 'Reciente'}")
        print(f"📢 Fuente: {fuente}")
        print(f"🔗 Link: {url}")
        print(f"🎯 Prioridad: {prioridad}/100")
        
        tech_list = []
        if "java" in cargo.lower(): tech_list.append("Java")
        if "spring" in cargo.lower(): tech_list.append("Spring Boot")
        if "react" in cargo.lower() or "react" in cargo.lower(): tech_list.append("React")
        if "python" in cargo.lower(): tech_list.append("Python")
        if "node" in cargo.lower() or "node.js" in cargo.lower(): tech_list.append("Node.js")
        if "javascript" in cargo.lower(): tech_list.append("JavaScript")
        if "typescript" in cargo.lower(): tech_list.append("TypeScript")
        if "full stack" in cargo.lower() or "fullstack" in cargo.lower() or "full-stack" in cargo.lower(): tech_list.append("Full Stack")
        if "backend" in cargo.lower() or "back-end" in cargo.lower() or "jvm" in cargo.lower(): tech_list.append("Backend")
        if "frontend" in cargo.lower() or "front-end" in cargo.lower(): tech_list.append("Frontend")
        if ".net" in cargo.lower(): tech_list.append(".NET")
        if "angular" in cargo.lower(): tech_list.append("Angular")
        if "azure" in cargo.lower(): tech_list.append("Azure")
        if "go" in cargo.lower() or "golang" in cargo.lower(): tech_list.append("Go")
        if "integration" in cargo.lower(): tech_list.append("Integración")        
        print(f"🔧 Tecnologías: {', '.join(tech_list) if tech_list else 'No especificadas'}")
        
        resumen = f"Vacante para {cargo} en {empresa}. "
        if modalidad == "Remoto":
            resumen += "Trabajo remoto desde Colombia. "
        if "java" in cargo.lower() and "spring" in cargo.lower():
            resumen += "✅ Coincide con Java + Spring Boot. "
        elif "java" in cargo.lower():
            resumen += "✅ Coincide con Java. "
        if "react" in cargo.lower():
            resumen += "✅ Usa React. "
        if "junior" in cargo.lower() or "trainee" in cargo.lower() or "aprendiz" in cargo.lower() or "practicante" in cargo.lower():
            resumen += "🎯 Ideal para primer empleo. "
        if "backend" in cargo.lower():
            resumen += "⚙️ Enfoque backend. "
        if "full" in cargo.lower():
            resumen += "🌐 Enfoque Full Stack. "
        print(f"📝 Resumen: {resumen}")
    
    print(f"\n{'='*60}")
    print(f"\n📊 Resumen: {len(deduped)} vacantes nuevas encontradas")
    print(f"👤 Perfil: Estudiante Ing. Sistemas | Java | Spring Boot | React | Full Stack")
    print(f"⏱ Próxima búsqueda en 30 minutos")
