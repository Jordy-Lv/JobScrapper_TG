#!/usr/bin/env python3
"""Final task: scrape 4 platforms for Colombian junior dev roles."""
import re, json, sys, os

KNOWN = {
    "4437761017","4437789098","4437853226","4437869373","4437911846",
    "4437931388","4437933092","4437934387","4437938300","4437943103",
    "4437947028","4438011823","4438028289","4438198772","4438199742",
    "4438221165","4438229623","4438254415","4438257236","4438258870",
    "4438268359","4438271135","4438300718","4438394330","4438541850",
    "4438542842","4438543781","4438546664","4438547014","4438548560",
    "4438548637","4438549554","4438549564","4438555356","4438555369",
    "4438556349","4438557278","4438557284","4438561079","4438580040",
    "4438630362","4438676331","4438693352","4438822694","4438823779",
    "4438833150","4438835887","4438844712","4438931714","4438953554",
    "4439051570","4439066096","4439089932","4439095693","4439103965",
    "4319944152","4320073545","4327949702","4343176860","4343246760",
    "4371035011","4378201702","4381550396","4381560087","4387739357",
    "4392806968","4392825106","4401781691","4408800638","4411793547",
    "4414370489","4418973156","4419320403","4420458796","4421695829",
    "4426004036","4426441045","4427352897","4428279046","4428536914",
    "4427352897","4431461515","4432281388","4432285380","4432692880",
    "4433991121","4435896034","4435919297","4436212620","4436228650",
    "4436230342","4436235313","4436241034","4436251635","4436258322",
    "4436278432","4436357818","4436516203","4436596634","4436603802",
    "4436629879","4436691216","4436808645","4436849191","4437044964",
    "4437075746","4437082261","4437097909","4437114876","4437184184",
    "4437470524","4437577079","4437598148","4437631003","4437724224",
    "4439312228","4439343144","4439360027","4439401999","4439410252",
    "4439413444","4439432312","4439432787","4439437738","4439437746",
    "4439440335","4439441337","4439446180","4439550581","4439862627",
    "4439862629","4439873853","4439885224","4439886276","4439889417",
    "4440006924","4440006937","4440006953","4440010709","4440013934",
    "4440014819","4440015754","4440018621","4440020686","4440022465",
    "4440023411","4440025408","4440029138","4440088945","4440272441",
    "4440342302","4440578559","4440962950","4440967485","4440970420",
    "4440971530","4440971699","4440973553","4440975060","4440975193",
    "4440975364","4440980319","4440981389","4440984921","4440985977",
    "4441201691","4441240860","4441253315","4441254499",
    "1886737347","72d44a3c","74cf79e0","bc80ef75",
    "1886737047",
    "qa-junior-bc-tecnologia-santiago",
    "junior-frontend-engineer-krunchbox-santiago",
    "desarrollador-a-junior-con-foco-en-ia-nico-seguros-santiago",
}

def unes(s):
    if not s: return ""
    for old, new in [("&#225;","á"),("&#233;","é"),("&#237;","í"),("&#243;","ó"),("&#250;","ú"),("&#241;","ñ"),("&amp;","&"),("&quot;",'"')]:
        s = s.replace(old, new)
    return s

def parse_ee(files):
    out = []
    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as f:
                html = f.read()
        except:
            continue
        for m in re.findall(r"data-ga4-offerdata=" + chr(34) + r"(\{.*?\})" + chr(34), html):
            try:
                d = json.loads(m.replace("&quot;",'"'))
            except:
                continue
            jid = str(d.get("id",""))
            if not jid or jid in KNOWN:
                continue
            t = d.get("title","")
            tl = t.lower()
            junior = any(k in tl for k in ["junior","jr.","jr ","trainee","practicante","aprendiz"])
            tech = any(k in tl for k in ["desarrollador","programador","ingeniero","analista","automatizador","qa","software","developer","test","pruebas","sap","soporte","tecnico","tech","consultor","datos","data","frontend","backend","full stack","devops","dev","infra"])
            if not (junior or tech):
                continue
            idx = html.find(jid)
            if idx >= 0:
                s = max(0,idx-5000)
                e = min(len(html),idx+5000)
                remote = "Remoto" in html[s:e]
            else:
                remote = False
            if not remote and "remoto" not in tl:
                continue
            out.append({
                "id": f"EE-{jid}",
                "raw_job_id": jid,
                "fuente": "El Empleo",
                "cargo": unes(t),
                "empresa": unes(d.get("company","No especifica")),
                "ciudad": "Remoto (Colombia)" if remote else unes(d.get("location","")),
                "modalidad": "Remoto",
                "experiencia": "Junior" if junior else "No especifica",
                "tecnologias": unes(d.get("tags","")),
                "contrato": "No especifica",
                "salario": unes(d.get("salary","No especifica")),
                "fecha": "",
                "url": f"https://www.elempleo.com/co/ofertas-trabajo/{t.lower().replace(' ','-')}-{jid}",
                "prioridad": "Alta",
            })
    return out

def parse_ro(fpath):
    out = []
    try:
        with open(fpath) as f:
            data = json.load(f)
    except:
        return out
    for job in (data[1:] if isinstance(data,list) and len(data)>1 else []):
        rid = str(job.get("id",""))
        if rid in KNOWN:
            continue
        loc = (job.get("location") or "").lower()
        if not any(k in loc for k in ["colombia","bogot","latin america","latam","latinoamerica","anywhere"]):
            continue
        pos = job.get("position","")
        if any(s in pos.lower() for s in ["senior","sr.","sr ","leader","lider","lead ","architect","principal","manager","chief","director","head "]):
            continue
        tags = [t.lower() for t in job.get("tags",[])]
        junior = any(k in pos.lower() for k in ["junior","jr.","jr ","entry","trainee"])
        tech = any(k in pos.lower() for k in ["developer","engineer","software","programador","desarrollador","java","react","frontend","backend","full stack","qa","data","python","javascript","devops"]) or any(t in {"junior","entry","java","react","full stack","spring","javascript","software","developer","engineer","frontend","backend","dev","qa","python"} for t in tags)
        if not (junior or tech):
            continue
        out.append({
            "id": f"RO-{rid}",
            "raw_job_id": rid,
            "fuente": "RemoteOK",
            "cargo": pos,
            "empresa": job.get("company",""),
            "ciudad": job.get("location",""),
            "modalidad": "Remoto",
            "experiencia": "Junior" if junior else "No especifica",
            "tecnologias": ", ".join(job.get("tags",[])),
            "contrato": "No especifica",
            "salario": f"{job.get('salary_min','')} - {job.get('salary_max','')}" if job.get('salary_min') or job.get('salary_max') else "No especifica",
            "fecha": job.get("date",""),
            "url": job.get("url",""),
            "prioridad": "Alta",
        })
    return out

def parse_gob(files):
    out = []
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
        except:
            continue
        for job in data.get("data",[]):
            a = job.get("attributes",{})
            jid = job.get("id","")
            if jid in KNOWN:
                continue
            if "Colombia" not in a.get("countries",[]):
                continue
            title = a.get("title","")
            if any(s in title.lower() for s in ["senior","sr.","sr ","leader","lider","lead ","architect","principal","manager","chief","director","head "]):
                continue
            co = a.get("company",{}).get("name","") if isinstance(a.get("company"),dict) else ""
            junior = any(k in title.lower() for k in ["junior","jr.","jr ","trainee","practicante"])
            tech = any(k in title.lower() for k in ["developer","engineer","software","desarrollador","java","react","frontend","backend","full stack","qa","data","python","javascript","devops","sdr"])
            if not (junior or tech):
                continue
            out.append({
                "id": f"GOB-{jid}",
                "raw_job_id": jid,
                "fuente": "GetOnBoard",
                "cargo": title,
                "empresa": co,
                "ciudad": ", ".join(a.get("countries",[])),
                "modalidad": a.get("remote_modality","Remoto") if a.get("remote") else "Presencial",
                "experiencia": "Junior" if junior else "No especifica",
                "tecnologias": "",
                "contrato": "No especifica",
                "salario": "No especifica",
                "fecha": str(a.get("published_at","")),
                "url": f"https://www.getonbrd.com/jobs/{jid}",
                "prioridad": "Alta",
            })
    return out

def parse_mag(fpath):
    return []

if __name__ == "__main__":
    base = "/home/ByLOGAN"
    all_new = []
    all_new.extend(parse_ee([os.path.join(base,f) for f in ["elempleo_output.txt","elempleo_java.txt","elempleo_spring.txt"]]))
    all_new.extend(parse_ro(os.path.join(base,"remoteok_output.txt")))
    all_new.extend(parse_gob([os.path.join(base,f) for f in ["getonboard_output.txt","gob_col.txt","gob_dev.txt","gob_react.txt","gob_all.txt","gob_js.txt","gob_java2.txt"]]))
    all_new.extend(parse_mag(os.path.join(base,"magneto_output.txt")))

    # Dedup by (company, title)
    seen = set()
    deduped = []
    for j in all_new:
        k = (j["empresa"].lower().strip(), j["cargo"].lower().strip())
        if k in seen:
            continue
        seen.add(k)
        deduped.append(j)

    if not deduped:
        print("[SILENT-OTHER]")
    else:
        print(json.dumps(deduped, indent=2, ensure_ascii=False))
