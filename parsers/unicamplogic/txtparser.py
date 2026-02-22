import os
import json
import re

def parse_unicamp_txt(input_file_path, chamada):
    """
    Parse do arquivo txt da UNICAMP para gender_intermediate.json
    """
    # Ler arquivo
    with open(input_file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    students = []
    lines = content.split('\n')
    
    # Regex para capturar os 3 grupos principais da linha
    # Grupo 1: (241498191) -> inscricao
    # Grupo 2: Abel Rapha de Jesus Macedo (***) -> nome_part (com cota)
    # Grupo 3: Matematica - Licenciatura (N) -> curso_part
    # O separador são 3 ou mais espaços
    line_regex = re.compile(r'^\((\d+)\)\s*(.*?)\s{3,}(.*)$')
    
    # Regex para extrair a cota do final do nome_part
    cota_regex = re.compile(r'(\s*\([\*\s]+\))$') # Ex: " (*)" ou " (***)"

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Tenta dar match na linha inteira
        match = line_regex.match(line)
        
        if match:
            try:
                inscricao = match.group(1)
                nome_part = match.group(2).strip()
                curso_part = match.group(3).strip()

                cota = None
                nome = nome_part
                
                # Verifica se o nome_part termina com uma cota
                cota_match = cota_regex.search(nome_part)
                if cota_match:
                    # Extrai a cota
                    cota = cota_match.group(1).strip()
                    # Limpa o nome, removendo a cota
                    nome = nome_part[:cota_match.start()].strip()
                
                # Limpar espaços extras do curso
                curso = re.sub(r'\s+', ' ', curso_part).strip()
                
                student = {
                    "inscricao": inscricao,  # <--- ADICIONADO
                    "nome": nome,
                    "cidade": None,
                    "universidade": "unicamp",
                    "campus": None,
                    "genero": None,
                    "chamada": chamada,
                    "curso": curso,
                    "cota": cota              # <--- ADICIONADO
                }
                students.append(student)
                
            except Exception as e:
                print(f"Erro ao processar linha: {line}")
                print(f"Erro: {e}")
                continue
    
    return students

def save_gender_intermediate(students, output_dir, acumular=False):
    """
    Salva o arquivo gender_intermediate.json
    """
    # Criar diretório se não existir
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "gender_intermediate.json")
    
    # Se acumular é True, carrega os estudantes existentes e adiciona os novos
    if acumular and os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                estudantes_existentes = json.load(f)
        except json.JSONDecodeError:
            estudantes_existentes = []
        
        # Combinar listas (evitando duplicatas baseado na inscricao)
        inscricoes_existentes = {s['inscricao'] for s in estudantes_existentes}
        novos_estudantes = [s for s in students if s['inscricao'] not in inscricoes_existentes]
        
        estudantes_combinados = estudantes_existentes + novos_estudantes
        print(f"📊 Acumulando: {len(estudantes_existentes)} existentes + {len(novos_estudantes)} novos = {len(estudantes_combinados)} totais")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(estudantes_combinados, f, ensure_ascii=False, indent=2)
        
        print(f"Arquivo gender_intermediate.json ATUALIZADO com {len(estudantes_combinados)} estudantes")
        
    else:
        # Salvar normalmente (sobrescrever) - COMPORTAMENTO PADRÃO
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(students, f, ensure_ascii=False, indent=2)
        
        chamada_atual = students[0]['chamada'] if students else 'N/A'
        print(f"📁 Salvando dados da chamada {chamada_atual} (sobrescrevendo)")
        print(f"Arquivo gender_intermediate.json salvo com {len(students)} estudantes")
    
    # Mostrar estatísticas da chamada atual
    chamada_atual = students[0]['chamada'] if students else 'N/A'
    total_com_cota = len([s for s in students if s['cota'] is not None])
    
    print(f"\n📊 Estatísticas da CHAMADA {chamada_atual} (Processados agora):")
    print(f"   - Total de estudantes: {len(students)}")
    print(f"   - Com cota (PAAIS/Etnico-racial): {total_com_cota}")
    
    return output_path

if __name__ == "__main__":
    # Exemplo de uso
    # Ajuste os caminhos conforme sua estrutura
    input_file = "Aprova2ch1.txt" # Assumindo que está na mesma pasta
    output_dir = "jsons_output/unicamp/" # Pasta de saída
    chamada = 1
    
    # Exemplo de como rodar múltiplas chamadas acumulando
    
    # --- Chamada 1 ---
    print("--- Processando Chamada 1 ---")
    students_c1 = parse_unicamp_txt(input_file, 1)
    save_gender_intermediate(students_c1, output_dir, acumular=False) # Sobrescreve
    
