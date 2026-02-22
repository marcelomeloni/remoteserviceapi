import os
import json
import re
import unicodedata 
from collections import defaultdict

def load_course_maps():
    """Carrega os mapas de curso para unidade e unidade para cidade dos arquivos existentes"""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        campus_map_path = os.path.join(base_dir, 'maps_universidade',  'campus_map.json')
        cidade_map_path = os.path.join(base_dir, 'maps_universidade', 'cidade_map.json')
        
        print(f"📂 Procurando mapas em:")
        print(f"   - {campus_map_path}")
        print(f"   - {cidade_map_path}")
        
        with open(campus_map_path, 'r', encoding='utf-8') as f:
            curso_to_unidades = json.load(f)
        
        with open(cidade_map_path, 'r', encoding='utf-8') as f:
            unidade_to_cidade = json.load(f)
        
        print(f"✅ Mapas carregados: {len(curso_to_unidades)} cursos, {len(unidade_to_cidade)} unidades")
        return curso_to_unidades, unidade_to_cidade
    
    except FileNotFoundError as e:
        print(f"❌ Erro ao carregar mapas: {e}")
        return {}, {}
    except Exception as e:
        print(f"❌ Erro inesperado ao carregar mapas: {e}")
        return {}, {}

def remove_accents(input_str):
    """
    Remove acentos da string (Ex: 'Ciência' -> 'Ciencia')
    """
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def clean_curso_name_for_lookup(curso):
    """Limpa REMANEJADO e espaços extras"""
    if not curso: return ""
    return curso.replace(" REMANEJADO", "").strip()

def remove_turno_final(curso):
    """
    Remove conteúdo entre parênteses no final da string.
    Ex: "Pedagogia (N)" -> "Pedagogia"
    """
    if not curso: return ""
    return re.sub(r'\s*\([^)]+\)\s*$', '', curso).strip()

def remove_licenciatura_suffix(curso):
    """
    Remove especificamente o trecho ' - Licenciatura'
    Ex: "Pedagogia - Licenciatura" -> "Pedagogia"
    """
    if not curso: return ""
    # Remove " - Licenciatura" (com ou sem espaços, case insensitive)
    return re.sub(r'\s*-\s*Licenciatura', '', curso, flags=re.IGNORECASE).strip()

def determine_campus_and_city(curso_original, curso_to_unidades, unidade_to_cidade):
    # Para buscar no mapa, PRECISAMOS do turno (ex: "Engenharia (N)")
    curso_busca = clean_curso_name_for_lookup(curso_original)
    
    if curso_busca not in curso_to_unidades:
        curso_busca_norm = " ".join(curso_busca.split())
        if curso_busca_norm in curso_to_unidades:
            curso_busca = curso_busca_norm
        else:
            return None, None
    
    unidades = curso_to_unidades[curso_busca]
    if not unidades: return None, None
    
    primeira_unidade = unidades[0]
    if primeira_unidade not in unidade_to_cidade: return primeira_unidade, None
    
    cidade = unidade_to_cidade[primeira_unidade]
    return primeira_unidade, cidade

def safe_json_load(file_path):
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return []
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Erro ao carregar {file_path}: {e}")
        return []

def process_campus_classification(input_file_path, output_dir):
    print("📁 Carregando mapas...")
    curso_to_unidades, unidade_to_cidade = load_course_maps()
    
    if not curso_to_unidades: return
    
    with open(input_file_path, 'r', encoding='utf-8') as f:
        students = json.load(f)
    
    if not students: return
    
    chamada_atual = students[0].get('chamada', 'N/A')
    print(f"🎯 Processando {len(students)} alunos da Chamada {chamada_atual}...")
    
    # Diretórios
    cities_dir = os.path.join(output_dir, "cities")
    chamadas_dir = os.path.join(output_dir, "chamadas")
    os.makedirs(cities_dir, exist_ok=True)
    os.makedirs(chamadas_dir, exist_ok=True)
    
    # Carregar acumulados
    students_by_city_acumulado = defaultdict(list)
    for cf in os.listdir(cities_dir):
        if cf.endswith('.json'):
            city = cf.replace('.json', '')
            data = safe_json_load(os.path.join(cities_dir, cf))
            students_by_city_acumulado[city] = data

    students_by_city_chamada = defaultdict(list)
    stats_chamada = defaultdict(int)
    stats_chamada['total'] = len(students)
    
    for student in students:
        raw_course = student.get('curso', '')
        
        # 1. Identifica Remanejado
        is_remanejado = "REMANEJADO" in raw_course
        
        # 2. Descobre Local
        unidade, cidade = determine_campus_and_city(raw_course, curso_to_unidades, unidade_to_cidade)
        
        # 3. GERA NOME LIMPO
        # Passo A: Tira "REMANEJADO"
        temp_name = clean_curso_name_for_lookup(raw_course)
        # Passo B: Tira Turno "(N)" / "(I)"
        temp_name = remove_turno_final(temp_name)
        # Passo C: Tira " - Licenciatura" (NOVO)
        temp_name = remove_licenciatura_suffix(temp_name)
        # Passo D: Tira Acentos
        curso_visual_limpo = remove_accents(temp_name)
        
        # Atualiza Student
        student['campus'] = cidade
        student['unidade'] = unidade
        student['remanejado'] = is_remanejado
        student['curso_limpo'] = curso_visual_limpo 
        
        # Stats e Agrupamento
        key_cidade = cidade if cidade else 'indeterminado'
        stats_chamada[key_cidade] += 1
        
        if cidade:
            students_by_city_chamada[cidade].append(student)
            students_by_city_acumulado[cidade].append(student)

    # Salvamento
    print(f"\n💾 Salvando Chamada {chamada_atual}...")
    
    for cidade, lista in students_by_city_chamada.items():
        path = os.path.join(chamadas_dir, cidade)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, f"c{chamada_atual}.json"), 'w', encoding='utf-8') as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
            
    print(f"💾 Atualizando acumulados...")
    for cidade, lista in students_by_city_acumulado.items():
        with open(os.path.join(cities_dir, f"{cidade}.json"), 'w', encoding='utf-8') as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Concluído! Estatísticas Chamada {chamada_atual}:")
    for k, v in stats_chamada.items():
        print(f"   - {k.capitalize()}: {v}")

    if students:
        print(f"\n🔍 Exemplo de limpeza:")
        print(f"   Original: '{students[0]['curso']}'")
        print(f"   Limpo:    '{students[0]['curso_limpo']}'")

    return students

if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    inp = os.path.join(base, "jsons", "unicamp", "campus_intermediate.json")
    out = os.path.join(base, "jsons", "unicamp")
    if os.path.exists(inp):
        process_campus_classification(inp, out)