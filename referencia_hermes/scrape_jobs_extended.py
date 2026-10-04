#!/usr/bin/env python3
"""
Job scraper: LinkedIn, Computrabajo, El Empleo, Magneto, RemoteOK, GetOnBoard
"""
import json
import re
import subprocess
import sys
import os
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

CURL_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def curl(url, timeout=20):
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "-H", f"User-Agent: {CURL_UA}", url],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0 and len(result.stdout) > 100:
            return result.stdout
        return ""
    except:
        return ""

def extract_linkedin_jobs(html, source_label):
    """Extract jobs from LinkedIn HTML"""
    jobs = []
    # Extract job cards
    # Find all job listing blocks
    pattern = r'data-entity-urn="urn:li:jobPosting:(\d+)"[^>]*>.*?<h3[^>]*class="base-search-card__title"[^>]*>\s*(.*?)\s*</h3>.*?<h4[^>]*class="base-search-card__subtitle"[^>]*>.*?<a[^>]*>\s*(.*?)\s*</a>.*?<span[^>]*class="job-search-card__location"[^>]*>\s*(.*?)\s*</span>.*?<time[^>]*datetime="([^"]*)"'
    
    matches = re.finditer(pattern, html, re.DOTALL)
    for m in matches:
        job_id = m.group(1)
        title = m.group(2).strip()
        company = m.group(3).strip()
        location = m.group(4).strip()
        date = m.group(5).strip()
        url = f"https://co.linkedin.com/jobs/view/{job_id}"
        
        jobs.append({
            "fuente": source_label,
            "cargo": title,
            "empresa": company,
            "ciudad": location,
            "url": url,
            "raw_job_id": job_id,
            "fecha": date,
            "experiencia": "Junior / Entry Level",
            "modalidad": "A determinar",
            "prioridad": 0,
            "es_prioritaria": False,
            "tecnologias": "",
            "salario": "",
            "tipo_contrato": "Por determinar",
            "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # Also try simpler regex pattern as fallback
    if len(jobs) == 0:
        # Try to extract from the HTML differently
        entities = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)
        titles = re.findall(r'<h3[^>]*class="base-search-card__title"[^>]*>\s*(.*?)\s*</h3>', html, re.DOTALL)
        companies = re.findall(r'class="hidden-nested-link"[^>]*>\s*(.*?)\s*</a>', html, re.DOTALL)
        locations = re.findall(r'class="job-search-card__location"[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL)
        dates = re.findall(r'<time[^>]*datetime="([^"]*)"', html)
        
        for i in range(min(len(entities), len(titles))):
            title = titles[i].strip() if i < len(titles) else ""
            company = companies[i].strip() if i < len(companies) else ""
            location = locations[i].strip() if i < len(locations) else ""
            date = dates[i].strip() if i < len(dates) else ""
            
            jobs.append({
                "fuente": source_label,
                "cargo": title,
                "empresa": company,
                "ciudad": location,
                "url": f"https://co.linkedin.com/jobs/view/{entities[i]}",
                "raw_job_id": entities[i],
                "fecha": date,
                "experiencia": "Junior / Entry Level",
                "modalidad": "A determinar",
                "prioridad": 0,
                "es_prioritaria": False,
                "tecnologias": "",
                "salario": "",
                "tipo_contrato": "Por determinar",
                "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    
    return jobs

def scrape_linkedin_all():
    """Scrape all LinkedIn search URLs"""
    all_jobs = []
    searches = [
        ("java+junior", "Colombia", "f_WT=2&f_TPR=r259200", 20),
        ("spring+boot+junior", "Colombia", "f_WT=2&f_TPR=r259200", 20),
        ("junior+desarrollador", "Cartagena", "f_TPR=r259200", 15),
        ("entry+level+software+developer", "Colombia", "f_TPR=r259200", 20),
        ("aprendiz+desarrollo+software", "Colombia", "f_TPR=r259200", 15),
        ("practicante+desarrollo", "Colombia", "f_TPR=r259200", 15),
        ("junior+frontend+react", "Colombia", "f_WT=2&f_TPR=r259200", 15),
        ("full+stack+junior", "Colombia", "f_WT=2&f_TPR=r259200", 15),
        ("junior+backend", "Colombia", "f_WT=2&f_TPR=r259200", 15),
        ("sin+experiencia+desarrollador", "Colombia", "f_TPR=r259200", 15),
        ("trainee+java", "Colombia", "f_TPR=r259200", 15),
    ]
    
    for kw, loc, extra, count in searches:
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={kw}&location={loc}&{extra}&start=0&count={count}"
        print(f"  LinkedIn: {kw}", file=sys.stderr)
        html = curl(url, timeout=25)
        if html:
            label = f"LinkedIn ({kw[:20]})"
            jobs = extract_linkedin_jobs(html, label)
            print(f"    -> {len(jobs)} jobs found", file=sys.stderr)
            all_jobs.extend(jobs)
        else:
            print(f"    -> Empty response for {kw}", file=sys.stderr)
        time.sleep(0.3)  # Rate limiting
    
    return all_jobs

def scrape_computrabajo():
    """Scrape Computrabajo Colombia"""
    all_jobs = []
    urls = [
        ("https://www.computrabajo.com.co/trabajo-de-desarrollador-junior?pubdate=3", "Computrabajo (desarrollador junior)"),
        ("https://www.computrabajo.com.co/trabajo-de-aprendiz-desarrollo-de-software?pubdate=3", "Computrabajo (aprendiz desarrollo)"),
        ("https://www.computrabajo.com.co/trabajo-de-practicante-desarrollo?pubdate=3", "Computrabajo (practicante desarrollo)"),
        ("https://www.computrabajo.com.co/trabajo-de-java-junior?pubdate=3", "Computrabajo (java junior)"),
        ("https://www.computrabajo.com.co/trabajo-de-programador-junior?pubdate=3", "Computrabajo (programador junior)"),
        ("https://www.computrabajo.com.co/trabajo-de-full-stack-junior?pubdate=3", "Computrabajo (full stack junior)"),
    ]
    
    for url, label in urls:
        print(f"  Computrabajo: {label.split('(')[1][:-1]}", file=sys.stderr)
        html = curl(url, timeout=20)
        if html:
            # Extract job links
            links = re.findall(r'href="(/ofertas-de-trabajo/[^"]+?en-[a-z-]+-[A-Z0-9]+)"', html)
            # Also try other patterns
            if not links:
                links = re.findall(r'href="(/oferta-de-trabajo/[^"]+)"', html)
            if not links:
                links = re.findall(r'href="(/ofertas-de-trabajo/[^"]+)"', html)
            
            print(f"    -> {len(links)} links found", file=sys.stderr)
            
            for link in links:
                full_url = f"https://www.computrabajo.com.co{link}"
                # Parse cargo y ciudad from URL
                parts = link.split('/')
                cargo = "Por determinar"
                ciudad = "Por determinar"
                
                # Try to extract from URL path
                url_match = re.search(r'en-([a-z-]+)-([A-Z0-9]+)', link)
                if url_match:
                    ciudad = url_match.group(1).replace('-', ' ').title()
                
                # Try to get title from URL
                title_match = re.search(r'/ofertas-de-trabajo/([^/]+?)(?:/|$)', link)
                if title_match:
                    cargo = title_match.group(1).replace('-', ' ').title()
                
                all_jobs.append({
                    "fuente": label,
                    "cargo": cargo,
                    "empresa": "Por determinar",
                    "ciudad": ciudad,
                    "url": full_url,
                    "raw_job_id": f"ct-{link[:50]}",
                    "fecha": datetime.now().strftime("%Y-%m-%d"),
                    "experiencia": "Junior / Entry Level",
                    "modalidad": "A determinar",
                    "prioridad": 0,
                    "es_prioritaria": False,
                    "tecnologias": "",
                    "salario": "",
                    "tipo_contrato": "Por determinar",
                    "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        else:
            print(f"    -> Empty response", file=sys.stderr)
        time.sleep(0.5)
    
    return all_jobs

def scrape_elempleo():
    """Scrape El Empleo"""
    print(f"  El Empleo", file=sys.stderr)
    url = "https://www.elempleo.com/co/ofertas-empleo/?busqueda=desarrollador+junior&modalidad=remoto&pagina=1"
    html = curl(url, timeout=20)
    jobs = []
    
    if html:
        # Extract job links
        links = re.findall(r'href="(/co/ofertas-trabajo/[^"]+?)"', html)
        links = list(set(links))
        print(f"    -> {len(links)} links found", file=sys.stderr)
        
        for link in links:
            full_url = f"https://www.elempleo.com{link}"
            job_id = f"elempleo-" + link.split('/')[-1] if '/' in link else link
            
            # Try to extract title from URL or HTML
            title_match = re.search(r'/ofertas-trabajo/([^/]+)', link)
            cargo = title_match.group(1).replace('-', ' ').title() if title_match else "Por determinar"
            
            jobs.append({
                "fuente": "El Empleo",
                "cargo": cargo,
                "empresa": "Por determinar",
                "ciudad": "Colombia",
                "url": full_url,
                "raw_job_id": job_id,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "experiencia": "Junior / Entry Level",
                "modalidad": "Remoto",
                "prioridad": 0,
                "es_prioritaria": False,
                "tecnologias": "",
                "salario": "",
                "tipo_contrato": "Por determinar",
                "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    else:
        print(f"    -> Empty or blocked", file=sys.stderr)
    
    return jobs

def scrape_magneto():
    """Scrape Magneto Empleos"""
    print(f"  Magneto Empleos", file=sys.stderr)
    url = "https://www.magnetoempleos.com.co/busqueda/?q=desarrollador+junior+remoto&page=1"
    html = curl(url, timeout=20)
    jobs = []
    
    if html:
        # Look for job listings
        links = re.findall(r'href="(/empleo/[^"]+)"', html)
        links = list(set(links))
        print(f"    -> {len(links)} links found", file=sys.stderr)
        
        for link in links:
            full_url = f"https://www.magnetoempleos.com.co{link}"
            
            cargo_match = re.search(r'/empleo/([^/]+)', link)
            cargo = cargo_match.group(1).replace('-', ' ').title() if cargo_match else "Por determinar"
            
            jobs.append({
                "fuente": "Magneto Empleos",
                "cargo": cargo,
                "empresa": "Por determinar",
                "ciudad": "Colombia",
                "url": full_url,
                "raw_job_id": f"mag-{link[:50]}",
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "experiencia": "Junior / Entry Level",
                "modalidad": "Remoto",
                "prioridad": 0,
                "es_prioritaria": False,
                "tecnologias": "",
                "salario": "",
                "tipo_contrato": "Por determinar",
                "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
    else:
        print(f"    -> Empty or blocked", file=sys.stderr)
    
    return jobs

def scrape_remoteok():
    """Scrape RemoteOK API"""
    print(f"  RemoteOK", file=sys.stderr)
    url = "https://remoteok.com/api"
    jobs = []
    
    data = curl(url, timeout=20)
    if data:
        try:
            all_jobs_data = json.loads(data)
            if isinstance(all_jobs_data, list) and len(all_jobs_data) > 1:
                # First element is usually metadata
                job_list = all_jobs_data[1:21] if len(all_jobs_data) > 1 else []
                print(f"    -> {len(job_list)} jobs from API", file=sys.stderr)
                
                for job in job_list:
                    if not isinstance(job, dict):
                        continue
                    
                    title = job.get('position', '')
                    company = job.get('company', '')
                    tags = [t.lower() for t in job.get('tags', [])]
                    title_lower = title.lower()
                    
                    # Filter: only junior/entry level positions
                    junior_keywords = ['junior', 'entry level', 'jr.', 'jr', 'trainee', 'graduate', 'intern']
                    is_junior = any(kw in title_lower for kw in junior_keywords)
                    
                    tech_tags = ['java', 'react', 'full stack', 'backend', 'frontend', 'javascript',
                                 'typescript', 'node', 'spring', 'html', 'css', 'mysql', 'python']
                    has_tech = any(t in tags for t in tech_tags) or any(t in title_lower for t in tech_tags)
                    
                    if not (is_junior or has_tech):
                        continue
                    
                    date_str = job.get('date', '')
                    if isinstance(date_str, str):
                        date_str = date_str[:10]
                    
                    url_job = job.get('url', '')
                    if url_job and not url_job.startswith('http'):
                        url_job = f"https://remoteok.com{url_job}"
                    
                    jobs.append({
                        "fuente": "RemoteOK",
                        "cargo": title,
                        "empresa": company,
                        "ciudad": "Remoto",
                        "url": url_job,
                        "raw_job_id": f"rok-{job.get('id', title[:30])}",
                        "fecha": date_str,
                        "experiencia": "Junior / Entry Level" if is_junior else "No especificado",
                        "modalidad": "Remoto",
                        "prioridad": 0,
                        "es_prioritaria": False,
                        "tecnologias": ", ".join(job.get('tags', [])),
                        "salario": job.get('salary', ''),
                        "tipo_contrato": "Por determinar",
                        "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
        except (json.JSONDecodeError, TypeError) as e:
            print(f"    -> JSON parse error: {e}", file=sys.stderr)
    else:
        print(f"    -> Empty response", file=sys.stderr)
    
    return jobs

def scrape_getonboard():
    """Scrape GetOnBoard API"""
    print(f"  GetOnBoard", file=sys.stderr)
    url = "https://www.getonbrd.com/api/v0/search/jobs?query=junior+java+spring&per_page=20"
    jobs = []
    
    data = curl(url, timeout=20)
    if data:
        try:
            resp = json.loads(data)
            job_data = resp.get('data', [])
            print(f"    -> {len(job_data)} jobs from API", file=sys.stderr)
            
            for item in job_data:
                if not isinstance(item, dict):
                    continue
                attrs = item.get('attributes', {})
                if not isinstance(attrs, dict):
                    attrs = {}
                cargo = attrs.get('title', '')
                
                # Get company name (defensive)
                company_name = ''
                relationships = item.get('relationships', {})
                if isinstance(relationships, dict):
                    company_rel = relationships.get('company', {})
                    if isinstance(company_rel, dict):
                        company_data = company_rel.get('data', {})
                        if isinstance(company_data, dict):
                            company_name = company_data.get('name', '')
                
                # Build URL
                slug = attrs.get('slug', '')
                job_url = f"https://www.getonbrd.com/jobs/{slug}" if slug else ''
                
                tags = attrs.get('tags', [])
                if not isinstance(tags, list):
                    tags = []
                tags_lower = [t.lower() for t in tags]
                
                jobs.append({
                    "fuente": "GetOnBoard",
                    "cargo": cargo,
                    "empresa": company_name,
                    "ciudad": attrs.get('remote', False) and 'Remoto LATAM' or attrs.get('country', ''),
                    "url": job_url,
                    "raw_job_id": f"gob-{slug or item.get('id', '')}",
                    "fecha": attrs.get('published_at', '')[:10] if attrs.get('published_at') else '',
                    "experiencia": "Junior / Entry Level",
                    "modalidad": "Remoto" if attrs.get('remote', False) else "Presencial",
                    "prioridad": 0,
                    "es_prioritaria": False,
                    "tecnologias": ", ".join(tags),
                    "salario": attrs.get('min_salary', ''),
                    "tipo_contrato": "Por determinar",
                    "fecha_descubrimiento": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
        except (json.JSONDecodeError, TypeError) as e:
            print(f"    -> JSON parse error: {e}", file=sys.stderr)
    else:
        print(f"    -> Empty response", file=sys.stderr)
    
    return jobs


def load_history(path):
    """Load existing job history"""
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get('vacantes', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(path, vacantes):
    """Save job history"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump({"vacantes": vacantes}, f, indent=2, ensure_ascii=False)

def is_duplicate(new_job, existing_jobs):
    """Check if a job is duplicate"""
    new_url = new_job.get('url', '').lower().strip()
    new_job_id = new_job.get('raw_job_id', '').lower().strip()
    new_cargo = new_job.get('cargo', '').lower().strip()
    new_empresa = new_job.get('empresa', '').lower().strip()
    
    for ej in existing_jobs:
        ej_url = ej.get('url', '')
        if not isinstance(ej_url, str):
            ej_url = ''
        ej_url = ej_url.lower().strip()
        
        ej_job_id = ej.get('raw_job_id', '')
        if not isinstance(ej_job_id, str):
            ej_job_id = ''
        ej_job_id = ej_job_id.lower().strip()
        
        ej_cargo = ej.get('cargo', '')
        if not isinstance(ej_cargo, str):
            ej_cargo = ''
        ej_cargo = ej_cargo.lower().strip()
        
        ej_empresa = ej.get('empresa', '')
        if not isinstance(ej_empresa, str):
            ej_empresa = ''
        ej_empresa = ej_empresa.lower().strip()
        
        # URL match
        if new_url and ej_url and new_url == ej_url:
            return True
        # Job ID match
        if new_job_id and ej_job_id and new_job_id == ej_job_id:
            return True
        # Company + Title match (fuzzy)
        if new_empresa and ej_empresa and new_cargo and ej_cargo:
            if new_empresa == ej_empresa and new_cargo == ej_cargo:
                return True
    
    return False

def assign_priority(job):
    """Assign priority score based on filters"""
    score = 0
    cargo = job.get('cargo', '')
    if not isinstance(cargo, str):
        cargo = ''
    cargo = cargo.lower()
    
    ciudad = job.get('ciudad', '')
    if not isinstance(ciudad, str):
        ciudad = ''
    ciudad = ciudad.lower()
    
    modalidad = job.get('modalidad', '')
    if not isinstance(modalidad, str):
        modalidad = ''
    modalidad = modalidad.lower()
    
    tecnologias = job.get('tecnologias', '')
    if not isinstance(tecnologias, str):
        tecnologias = ''
    tecnologias = tecnologias.lower()
    
    empresa = job.get('empresa', '')
    if not isinstance(empresa, str):
        empresa = ''
    empresa = empresa.lower()
    
    # Remoto desde Colombia = +40
    if 'remoto' in modalidad and ('colombia' in ciudad or 'remoto' in ciudad):
        score += 40
    elif 'remoto' in modalidad:
        score += 30
    
    # Cartagena = +30
    if 'cartagena' in ciudad:
        score += 30
    
    # Java + Spring Boot = +25
    if 'java' in cargo or 'java' in tecnologias:
        score += 15
        if 'spring' in cargo or 'spring' in tecnologias:
            score += 10
    
    # Backend = +15
    if 'backend' in cargo or 'backend' in tecnologias or 'back end' in cargo:
        score += 15
    
    # Full Stack = +12
    if 'full stack' in cargo or 'fullstack' in cargo or 'full-stack' in cargo:
        score += 12
    
    # React = +10
    if 'react' in cargo or 'react' in tecnologias:
        score += 10
    
    # Sin experiencia / Junior = +10
    if 'junior' in cargo or 'trainee' in cargo or 'sin experiencia' in cargo:
        score += 10
    
    # Contrato aprendizaje / prácticas = +5
    if 'aprendiz' in cargo or 'practicante' in cargo or 'pasante' in cargo or 'intern' in cargo:
        score += 5
    
    # BairesDev generic posts get lower score
    if 'bairesdev' in empresa and score > 20:
        score -= 10
    
    job['prioridad'] = score
    job['es_prioritaria'] = score >= 70
    
    return job

def is_valid_job(job):
    """Filter valid jobs by experience and area"""
    cargo = job.get('cargo', '')
    if not isinstance(cargo, str):
        cargo = ''
    cargo_lower = cargo.lower()
    
    tecnologias = job.get('tecnologias', '')
    if not isinstance(tecnologias, str):
        tecnologias = ''
    tecnologias_lower = tecnologias.lower()
    
    empresa = job.get('empresa', '')
    if not isinstance(empresa, str):
        empresa = ''
    empresa_lower = empresa.lower()
    
    ciudad = job.get('ciudad', '')
    if not isinstance(ciudad, str):
        ciudad = ''
    ciudad_lower = ciudad.lower()
    
    modalidad_lower = job.get('modalidad', '').lower()
    
    # REJECT senior positions
    senior_words = ['senior', 'sr.', 'sr ', 'líder', 'lider', 'arquitecto', 'architect', 
                    'tech lead', 'manager', 'director', 'head of', 'principal',
                    'lead ', 'lead_']
    if any(word in cargo_lower for word in senior_words):
        return False
    
    # REJECT >1 year experience indicators
    exp_high = ['años de experiencia', '2 años', '3 años', '4 años', '5 años', 
                '6 años', '7 años', '8 años', '9 años', '10 años']
    if any(word in cargo_lower for word in exp_high):
        return False
    
    # REJECT "Mid Level" - we want only junior/entry level
    if 'mid level' in cargo_lower or 'mid-level' in cargo_lower:
        return False
    
    # Reject clearly non-dev roles (strong reject)
    non_dev_keywords = [
        'contador', 'contable', 'financiero', 'finanzas', 'contabilidad',
        'administrativo', 'asistente administrativo', 'secretario/a', 'secretario',
        'ventas', 'comercial', 'marketing', 'community manager',
        'conductor', 'chofer', 'mensajero', 'domiciliario',
        'enfermero', 'medico', 'doctor', 'odontologo',
        'abogado', 'juridico', 'legal',
        'docente', 'profesor', 'maestro',
        'cajero', 'vendedor', 'asesor comercial',
        'operario', 'produccion', 'producción',
        'seguridad', 'vigilante',
        'recepcionista', 'mesero', 'cocinero',
        'diseñador grafico', 'diseñador gráfico', 'diseñador grafico',
        'logistica', 'logística',
        'auxiliar contable', 'auxiliar administrativo',
        'prestaciones economicas', 'arl', 'prestaciones económicas',
        'seguridad de la información', 'iso 27001',
        'derecho', 'abogacia',
        'gestion humana', 'gestión humana', 'recursos humanos', 'talento humano',
        'sst ', 'salud ocupacional', 'seguridad y salud',
        'ambiental', 'ambientales',
        'comunicaciones', 'comunicacion',
        'bizops', 'business operations',
        'make up', 'makeup', 'maquillaje', 'esteticista', 'esthetician',
        'capacitación', 'capacitacion', 'training',
        'contralor', 'auditor', 'auditoria', 'auditoría',
        'digital designer', 'graduate analyst', 'graduate program',
        'digital nomad',
    ]
    
    if any(word in cargo_lower for word in non_dev_keywords):
        return False
    
    # STRONG dev keywords that clearly indicate a dev role
    strong_dev_keywords = [
        'desarrollador', 'developer', 'software', 'programador', 'programmer',
        'ingeniero de sistemas', 'ingeniero en sistemas',
        'frontend', 'front-end', 'front end',
        'backend', 'back-end', 'back end',
        'full stack', 'fullstack', 'full-stack',
        'java', 'spring boot', 'springboot',
        'react', 'javascript', 'typescript', 'node.js', 'nodejs',
        'web developer', 'web programmer',
        'soporte ti', 'soporte técnico', 'soporte tecnico', 'it support',
        'api', 'rest api', 'microservicios',
        'aplicaciones', 'app developer',
        'code', 'coder', 'coding',
        'trainee', 'aprendiz', 'practicante', 'pasante',
        'junior', 'entry level', 'entry-level',
        'analista de desarrollo', 'analista de sistemas',
        'automatizacion', 'automatización', 'automation',
        'qa', 'quality assurance', 'pruebas',
        'devops', 'cloud',
        'sql', 'mysql', 'postgresql', 'base de datos', 'database',
        '.net', 'python', 'php', 'angular', 'vue',
        'git', 'github', 'docker',
        'soporte', 'support',
        'internship', 'intern', 'pasantía', 'pasantia',
        'reingeniería', 'reingenieria',
    ]
    
    if not any(word in cargo_lower for word in strong_dev_keywords):
        # Check tecnologias for dev context - require at least 2 tech tags
        tech_tags = ['java', 'react', 'javascript', 'python', 'sql', 'html', 'css', 'node', 'angular', 'spring', 'docker', 'git', 'api', 'backend', 'frontend', 'full stack', 'typescript', 'php', '.net', 'devops', 'cloud', 'mysql', 'postgresql']
        tech_matches = [t for t in tech_tags if t in tecnologias_lower]
        if len(tech_matches) < 2:
            # For RemoteOK specifically, only trust if cargo itself has dev keywords
            if job.get('fuente', '').startswith('RemoteOK'):
                return False
            return False
    
    # Extra filter: reject "practicante" and "aprendiz" when combined with non-dev areas
    sales_marketing_hr = ['sales', 'ventas', 'marketing', 'comercial', 'hr ', 'rrhh', 'recursos humanos',
                          'product management', 'product manager', 'gestión humana', 'gestion humana']
    if 'practicante' in cargo_lower or 'aprendiz' in cargo_lower or 'pasante' in cargo_lower:
        if any(word in cargo_lower for word in sales_marketing_hr):
            return False
        # For practicante/pasante roles without a specific tech keyword, require "sistemas", "software", "informatica" etc
        tech_context = ['sistemas', 'software', 'informatica', 'informática', 'tecnologia', 'tecnología',
                        'ti', 'it ', 'desarrollo', 'programación', 'programacion',
                        'datos', 'data', 'analytics', 'analitica']
        if not any(word in cargo_lower for word in tech_context + strong_dev_keywords):
            return False
        # Also require at least a technical degree mention
        tech_degrees = ['ingeniería', 'ingenieria', 'sistemas', 'informatica', 'informática']
        if not any(word in cargo_lower for word in tech_degrees + strong_dev_keywords):
            return False
    
    # Extra filter: "analista" without dev/tech context
    if 'analista' in cargo_lower:
        non_dev_analyst = ['procesos', 'negocio', 'business', 'financiero', 'contable', 'compras',
                           'inventarios', 'logistica', 'logística', 'calidad', 'credito', 'crédito']
        if any(word in cargo_lower for word in non_dev_analyst):
            return False
    
    # Location filter: only Colombia, Remoto, Cartagena
    acceptable_location = ('remoto' in ciudad_lower or 
                          'colombia' in ciudad_lower or 
                          'cartagena' in ciudad_lower or
                          'latam' in ciudad_lower or
                          'remote' in ciudad_lower)
    
    if not acceptable_location and not any(word in modalidad_lower for word in ['remoto', 'remote']):
        # Allow other Colombian cities but deprioritize
        pass  # We'll keep them with lower priority
    
    return True

def filter_and_dedupe(all_new_jobs, history):
    """Filter valid jobs, deduplicate against history"""
    # Filter valid
    valid_jobs = [j for j in all_new_jobs if is_valid_job(j)]
    
    # Deduplicate
    seen_urls = set()
    seen_ids = set()
    unique_jobs = []
    
    for j in valid_jobs:
        url = j.get('url', '').strip().lower()
        jid = j.get('raw_job_id', '').strip().lower()
        
        if url and url in seen_urls:
            continue
        if jid and jid in seen_ids:
            continue
        
        if url:
            seen_urls.add(url)
        if jid:
            seen_ids.add(jid)
        
        unique_jobs.append(j)
    
    # Check against history
    truly_new = [j for j in unique_jobs if not is_duplicate(j, history)]
    
    # Assign priorities
    for j in truly_new:
        assign_priority(j)
    
    # Sort by priority (descending)
    truly_new.sort(key=lambda x: x['prioridad'], reverse=True)
    
    return truly_new

def main():
    path = os.path.expanduser("~/.hermes/cron/output/historial_vacantes.json")
    history = load_history(path)
    print(f"Historial existente: {len(history)} vacantes", file=sys.stderr)
    
    all_jobs = []
    
    print("=== Scraping LinkedIn ===", file=sys.stderr)
    all_jobs.extend(scrape_linkedin_all())
    
    print("\n=== Scraping Computrabajo ===", file=sys.stderr)
    all_jobs.extend(scrape_computrabajo())
    
    print("\n=== Scraping El Empleo ===", file=sys.stderr)
    all_jobs.extend(scrape_elempleo())
    
    print("\n=== Scraping Magneto ===", file=sys.stderr)
    all_jobs.extend(scrape_magneto())
    
    print("\n=== Scraping RemoteOK ===", file=sys.stderr)
    all_jobs.extend(scrape_remoteok())
    
    print("\n=== Scraping GetOnBoard ===", file=sys.stderr)
    all_jobs.extend(scrape_getonboard())
    
    print(f"\n=== Total raw jobs scraped: {len(all_jobs)} ===", file=sys.stderr)
    
    new_jobs = filter_and_dedupe(all_jobs, history)
    print(f"Vacantes NUEVAS (no duplicadas): {len(new_jobs)}", file=sys.stderr)
    
    # Output JSON for consumption
    result = {
        "total_raw": len(all_jobs),
        "nuevas": len(new_jobs),
        "vacantes_nuevas": new_jobs,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # Save to history
    if new_jobs:
        updated_history = history + new_jobs
        save_history(path, updated_history)
        print(f"Historial actualizado: {len(updated_history)} vacantes", file=sys.stderr)

if __name__ == "__main__":
    main()
