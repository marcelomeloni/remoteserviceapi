from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import json
import os
import sys
import uuid
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client, Client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from parsers.unicamplogic.txtparser import parse_unicamp_txt
from parsers.unicamplogic.campus_parser import (
    remove_accents,
    clean_curso_name_for_lookup,
    remove_turno_final,
    remove_licenciatura_suffix,
)

# ─── Supabase setup ───────────────────────────────────────────────────────────
load_dotenv(os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
TABLE_NAME   = "master_calouros"

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado.")
    except Exception as e:
        print(f"⚠️  Supabase não conectado: {e}")
else:
    print("⚠️  SUPABASE_URL / SUPABASE_SERVICE_KEY não encontrados no .env — modo JSON only.")

# ─── Flask ────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

staging = {}


# ─── Helpers de parse ─────────────────────────────────────────────────────────

def detect_university_and_chamada(url: str):
    url_lower = url.lower()
    university = "unicamp" if "unicamp" in url_lower or "comvest" in url_lower else "unknown"
    chamada_match = re.search(r"chamada(\d+)", url_lower)
    chamada = int(chamada_match.group(1)) if chamada_match else 1
    return university, chamada


def parse_html_to_students(html: str, chamada: int, university: str):
    soup = BeautifulSoup(html, "html.parser")
    pre = soup.find("pre")
    if not pre:
        return [], "Nenhum bloco <pre> encontrado na página."

    tmp_path = os.path.join(BASE_DIR, "_tmp_scrape.txt")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(pre.get_text())

    try:
        students = parse_unicamp_txt(tmp_path, chamada)
        for s in students:
            s["universidade"] = university
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return students, None


def load_json_map(relative_path: str):
    full = os.path.join(BASE_DIR, relative_path)
    if not os.path.exists(full):
        return {}
    with open(full, "r", encoding="utf-8") as f:
        return json.load(f)


def classify_gender_inline(students: list):
    gender_map = load_json_map("maps_universidade/gender_map.json")
    for s in students:
        nome = s.get("nome", "")
        primeiro = nome.split()[0].upper() if nome else ""
        genero = gender_map.get(primeiro, gender_map.get(
            re.sub(r"[^A-Z]", "", primeiro), "I"
        ))
        s["genero"] = genero
    return students


def classify_campus_inline(students: list):
    curso_to_unidades = load_json_map("maps_universidade/campus_map.json")
    unidade_to_cidade = load_json_map("maps_universidade/cidade_map.json")

    if not curso_to_unidades:
        return students

    for s in students:
        raw = s.get("curso", "")
        busca = clean_curso_name_for_lookup(raw)

        unidades = curso_to_unidades.get(busca) or curso_to_unidades.get(" ".join(busca.split()))
        if not unidades:
            continue

        unidade = unidades[0]
        cidade = unidade_to_cidade.get(unidade)
        s["campus"] = cidade
        s["unidade"] = unidade

        temp = clean_curso_name_for_lookup(raw)
        temp = remove_turno_final(temp)
        temp = remove_licenciatura_suffix(temp)
        s["curso_limpo"] = remove_accents(temp)

    return students


def build_summary(students: list):
    total = len(students)
    by_gender  = defaultdict(int)
    by_campus  = defaultdict(int)
    by_cota    = defaultdict(int)

    for s in students:
        by_gender[s.get("genero", "I")] += 1
        by_campus[s.get("campus") or "indeterminado"] += 1
        by_cota[s.get("cota") or "sem_cota"] += 1

    return {
        "total": total,
        "por_genero": dict(by_gender),
        "por_campus": dict(by_campus),
        "por_cota":   dict(by_cota),
    }


# ─── Supabase: transform + upload (lógica do seu upload_script.py) ────────────

def transform_for_supabase(students: list):
    """Converte os campos do JSON para o schema da tabela master_calouros."""
    rows = {}
    skipped = 0

    for s in students:
        inscricao    = s.get("inscricao")
        nome         = s.get("nome")
        curso        = s.get("curso_limpo") or s.get("curso")
        cidade_valor = s.get("campus")   # "campus" no JSON → coluna "cidade" no DB
        unidade_val  = s.get("unidade")

        # Campos obrigatórios
        if not inscricao or not nome or not curso or not cidade_valor:
            skipped += 1
            continue

        # Mapeamento de gênero
        g = s.get("genero", "I")
        genero_db = "male" if g == "M" else "female" if g == "F" else "other"

        rows[inscricao] = {
            "inscricao":  inscricao,
            "name":       nome,
            "course":     curso,
            "university": s.get("universidade"),
            "cidade":     cidade_valor,
            "unidade":    unidade_val,
            "chamada":    s.get("chamada"),
            "genero":     genero_db,
            "cota":       s.get("cota"),
            "remanejado": s.get("remanejado", False),
        }

    return list(rows.values()), skipped


def upload_to_supabase(students: list):
    """
    Faz upsert no Supabase. Retorna (ok: bool, mensagem: str, detalhes: dict).
    """
    if not supabase:
        return False, "Supabase não configurado (.env ausente ou inválido)", {}

    rows, skipped = transform_for_supabase(students)

    if not rows:
        return False, "Nenhum registro válido para enviar (todos pulados por dados faltando)", {
            "skipped": skipped
        }

    try:
        response = supabase.table(TABLE_NAME).upsert(
            rows,
            on_conflict="inscricao"
        ).execute()

        inserted = len(response.data) if response.data else 0

        return True, f"✅ {inserted} registros enviados ao Supabase!", {
            "inserted": inserted,
            "skipped":  skipped,
            "total_processados": len(rows),
        }

    except Exception as e:
        msg = getattr(e, "message", str(e))
        return False, f"Erro no upload ao Supabase: {msg}", {"skipped": skipped}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/api/parse", methods=["POST"])
def parse_url():
    body = request.get_json(force=True)
    url  = (body or {}).get("url", "").strip()

    if not url:
        return jsonify({"error": "URL não informada"}), 400

    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; UniParser/1.0)"
        })
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except Exception as e:
        return jsonify({"error": f"Falha ao buscar URL: {str(e)}"}), 502

    university, chamada = detect_university_and_chamada(url)
    students, parse_error = parse_html_to_students(resp.text, chamada, university)

    if parse_error:
        return jsonify({"error": parse_error}), 422
    if not students:
        return jsonify({"error": "Nenhum estudante encontrado. Verifique a URL."}), 422

    students = classify_gender_inline(students)
    students = classify_campus_inline(students)

    summary  = build_summary(students)
    job_id   = str(uuid.uuid4())

    staging[job_id] = {
        "students":   students,
        "url":        url,
        "university": university,
        "chamada":    chamada,
        "summary":    summary,
        "status":     "pending",
    }

    return jsonify({
        "job_id":     job_id,
        "university": university,
        "chamada":    chamada,
        "summary":    summary,
        "preview":    students[:10],
        "total":      len(students),
    })


@app.route("/api/confirm/<job_id>", methods=["POST"])
def confirm_job(job_id):
    job = staging.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado ou já confirmado"}), 404
    if job["status"] != "pending":
        return jsonify({"error": "Job já foi processado"}), 409

    students   = job["students"]
    university = job["university"]
    chamada    = job["chamada"]

    result = {
        "chamada":    chamada,
        "university": university,
        "total":      len(students),
        "supabase":   None,
        "json_files": None,
    }

    # ── 1. Upload Supabase ────────────────────────────────────────────────────
    ok, msg, details = upload_to_supabase(students)
    result["supabase"] = {"ok": ok, "message": msg, **details}

    # ── 2. Salva JSONs locais (backup sempre) ─────────────────────────────────
    output_dir  = os.path.join(BASE_DIR, "jsons", university)
    cities_dir  = os.path.join(output_dir, "cities")
    chamadas_dir = os.path.join(output_dir, "chamadas")
    os.makedirs(cities_dir,   exist_ok=True)
    os.makedirs(chamadas_dir, exist_ok=True)

    by_city = defaultdict(list)
    for s in students:
        by_city[s.get("campus") or "indeterminado"].append(s)

    for city, lst in by_city.items():
        path = os.path.join(chamadas_dir, city)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, f"c{chamada}.json"), "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)

    for city, lst in by_city.items():
        city_file = os.path.join(cities_dir, f"{city}.json")
        existing  = []
        if os.path.exists(city_file):
            try:
                with open(city_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        existing_ids = {s.get("inscricao") for s in existing}
        new_entries  = [s for s in lst if s.get("inscricao") not in existing_ids]
        with open(city_file, "w", encoding="utf-8") as f:
            json.dump(existing + new_entries, f, ensure_ascii=False, indent=2)

    full_path = os.path.join(output_dir, f"chamada_{chamada}_full.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)

    result["json_files"] = {
        "full_dump":    full_path,
        "cities_dir":  cities_dir,
        "chamadas_dir": chamadas_dir,
    }

    job["status"] = "confirmed"

    # Mensagem principal para o frontend
    if ok:
        result["message"] = f"✅ {len(students)} estudantes salvos no Supabase + backup JSON!"
    else:
        result["message"] = f"⚠️ Supabase falhou, mas JSON salvo localmente. ({msg})"

    return jsonify(result)


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    if job_id in staging:
        del staging[job_id]
    return jsonify({"message": "Job cancelado."})


@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = staging.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404
    return jsonify({
        "job_id":     job_id,
        "status":     job["status"],
        "university": job["university"],
        "chamada":    job["chamada"],
        "total":      len(job["students"]),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

