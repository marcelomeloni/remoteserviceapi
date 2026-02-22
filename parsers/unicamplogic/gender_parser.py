import os
import json
import re

def load_gender_map(gender_map_path):
    """Carrega o dicionário de gênero do arquivo JSON"""
    with open(gender_map_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def determine_gender(nome_completo, gender_map):
    """
    Determina o gênero baseado no primeiro nome usando o gender_map
    """
    # Pegar apenas o primeiro nome
    primeiro_nome = nome_completo.split()[0].upper() if nome_completo else ""
    
    # Tentar encontrar no gender_map
    if primeiro_nome in gender_map:
        return gender_map[primeiro_nome]
    
    # Se não encontrou, tentar variações comuns
    # Remover acentos e caracteres especiais
    nome_sem_acentos = re.sub(r'[^A-Z]', '', primeiro_nome)
    if nome_sem_acentos in gender_map:
        return gender_map[nome_sem_acentos]
    
    # Tentar com nomes compostos (ex: "Maria Clara" -> "MARIA")
    if ' ' in nome_completo:
        primeiro_nome_composto = nome_completo.split()[0].upper()
        if primeiro_nome_composto in gender_map:
            return gender_map[primeiro_nome_composto]
    
    return "I"  # Indeterminado (em vez de None)

def process_gender_classification(input_file_path, gender_map_path, output_file_path):
    """
    Processa a classificação de gênero para todos os estudantes
    """
    # Carregar gender_map
    print("Carregando gender_map...")
    gender_map = load_gender_map(gender_map_path)
    print(f"Gender_map carregado com {len(gender_map)} entradas")
    
    # Carregar estudantes do arquivo intermediário
    with open(input_file_path, 'r', encoding='utf-8') as f:
        students = json.load(f)
    
    print(f"Processando gênero para {len(students)} estudantes...")
    
    # Estatísticas
    stats = {
        'total': len(students),
        'masculino': 0,
        'feminino': 0,
        'indeterminado': 0
    }
    
    nomes_nao_identificados = []
    
    # Processar cada estudante
    for student in students:
        genero = determine_gender(student['nome'], gender_map)
        student['genero'] = genero
        
        # Atualizar estatísticas
        if genero == 'M':
            stats['masculino'] += 1
        elif genero == 'F':
            stats['feminino'] += 1
        else:  # "I" para indeterminado
            stats['indeterminado'] += 1
            # Salvar informações do estudante não identificado
            primeiro_nome = student['nome'].split()[0].upper() if student['nome'] else ""
            nomes_nao_identificados.append({
                'nome_completo': student['nome'],
                'primeiro_nome': primeiro_nome,
                'curso': student['curso'],
                'chamada': student['chamada']
            })
    
    # Salvar arquivo atualizado (com "I" para gêneros indeterminados)
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(students, f, ensure_ascii=False, indent=2)
    
    # Salvar lista de nomes não identificados para análise
    output_dir = os.path.dirname(output_file_path)
    nomes_nao_id_file = os.path.join(output_dir, "nomes_nao_identificados.json")
    with open(nomes_nao_id_file, 'w', encoding='utf-8') as f:
        json.dump(nomes_nao_identificados, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Classificação de gênero concluída!")
    print(f"📊 Estatísticas:")
    print(f"   - Masculino (M): {stats['masculino']} ({stats['masculino']/stats['total']*100:.1f}%)")
    print(f"   - Feminino (F): {stats['feminino']} ({stats['feminino']/stats['total']*100:.1f}%)")
    print(f"   - Indeterminado (I): {stats['indeterminado']} ({stats['indeterminado']/stats['total']*100:.1f}%)")
    
    # Mostrar nomes não identificados
    if nomes_nao_identificados:
        print(f"\n🔍 Nomes não identificados ({len(nomes_nao_identificados)}):")
        print("Primeiros nomes únicos não encontrados no gender_map:")
        
        # Pegar primeiros nomes únicos
        primeiros_nomes_unicos = sorted(set([item['primeiro_nome'] for item in nomes_nao_identificados]))
        
        for i, primeiro_nome in enumerate(primeiros_nomes_unicos[:20]):  # Mostrar até 20
            print(f"   {i+1}. {primeiro_nome}")
        
        if len(primeiros_nomes_unicos) > 20:
            print(f"   ... e mais {len(primeiros_nomes_unicos) - 20} nomes")
        
        print(f"\n💾 Lista completa salva em: {nomes_nao_id_file}")
        
        # Mostrar alguns exemplos completos
        print("\n🧪 Exemplos de estudantes com gênero indeterminado (I):")
        for i, exemplo in enumerate(nomes_nao_identificados[:5]):
            print(f"   {i+1}. {exemplo['nome_completo'][:30]}...")
            print(f"      Primeiro nome: {exemplo['primeiro_nome']}")
            print(f"      Curso: {exemplo['curso'][:30]}...")
            print(f"      Chamada: {exemplo['chamada']}")
            print(f"      Gênero atribuído: I")
    
    # Mostrar exemplos de classificação bem-sucedida
    print("\n✅ Exemplos de classificação bem-sucedida:")
    exemplos_identificados = [s for s in students if s['genero'] in ['M', 'F']][:3]
    for i, exemplo in enumerate(exemplos_identificados):
        print(f"   {i+1}. {exemplo['nome'][:25]}... -> {exemplo['genero']}")
    
    return students

if __name__ == "__main__":
    # Configurações de caminho
    input_file = "../../jsons/unicamp/gender_intermediate.json"
    gender_map_file = "../../maps_universidade/gender_map.json"
    output_file = "../../jsons/unicamp/campus_intermediate.json"
    
    process_gender_classification(input_file, gender_map_file, output_file)