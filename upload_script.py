import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client
import sys

# --- CONFIGURAÇÃO ---
# 1. O nome do arquivo JSON agora será pego da linha de comando (sys.argv[1])

# 2. Nome da tabela no Supabase
TABLE_NAME = "master_calouros"

# 3. Coluna de conflito (Chave Única para o Upsert)
CONFLICT_COLUMN = "inscricao"
# --------------------


def load_env_vars():
    """Carrega as variáveis de ambiente e valida."""
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not url:
        print("❌ Erro: SUPABASE_URL não encontrada no arquivo .env", file=sys.stderr)
        sys.exit(1)
    if not key:
        print("❌ Erro: SUPABASE_SERVICE_KEY não encontrada no arquivo .env", file=sys.stderr)
        print("   (Lembre-se: esta deve ser a chave 'service_role' para ter permissão de escrita)", file=sys.stderr)
        sys.exit(1)
        
    return url, key

def connect_to_supabase(url, key):
    """Tenta conectar ao Supabase."""
    try:
        print("🚀 Conectando ao Supabase...")
        supabase: Client = create_client(url, key)
        print("✅ Conexão estabelecida.")
        return supabase
    except Exception as e:
        print(f"❌ Erro ao conectar ao Supabase: {e}", file=sys.stderr)
        sys.exit(1)

def load_json_file(filename):
    """Carrega o arquivo JSON do disco."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"📁 Arquivo '{filename}' lido com sucesso. ({len(data)} registros encontrados)")
        return data
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo JSON '{filename}' não encontrado.", file=sys.stderr)
        print("   (Verifique se o arquivo está na mesma pasta que o script)", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Erro: O arquivo '{filename}' não é um JSON válido.", file=sys.stderr)
        sys.exit(1)

def transform_data(students_list: list):
    """
    Transforma os dados do JSON para o schema exato do banco de dados
    E REMOVE DUPLICATAS baseadas na 'inscricao'.
    """
    print("🧬 Transformando e de-duplicando dados...")
    
    data_to_insert_dict = {}
    
    for student in students_list:
        # Mapeamento de Gênero
        genero_db = 'other'
        genero_json = student.get("genero")
        if genero_json == 'M':
            genero_db = 'male'
        elif genero_json == 'F':
            genero_db = 'female'

        inscricao = student.get("inscricao")

        if not inscricao or not student.get("nome") or not student.get("curso"):
            print(f"⚠️ Aviso: Pulando registro por falta de dados essenciais: {student}")
            continue

        # --- INÍCIO DA CORREÇÃO ---
        # Baseado no seu JSON:
        # "campus": "campinas"  <- Este é o valor que deve ir para a coluna 'cidade'
        # "unidade": "IMECC"     <- Este é o valor que deve ir para a coluna 'unidade'

        cidade_para_db = student.get("campus")
        unidade_para_db = student.get("unidade")

        # Validação CRÍTICA para a coluna 'cidade' (que é NOT NULL no DB)
        if not cidade_para_db:
             print(f"⚠️ Aviso: Pulando registro '{inscricao}'. A chave 'campus' (que usamos para 'cidade') está nula.")
             continue
        
        # Mapeamento de Campos (JSON -> DB)
        new_row = {
            # DB Column      <-- JSON Key
            "inscricao":    inscricao,
            "name":         student.get("nome"),
            "course":       student.get("curso_limpo"),
            "university":   student.get("universidade"),
            
            # Mapeamento CORRIGIDO de local
            "cidade":       cidade_para_db,     # (JSON "campus")
            "unidade":      unidade_para_db,    # (JSON "unidade")
            
            "chamada":      student.get("chamada"),
            "genero":       genero_db,
            "cota":         student.get("cota"),
            "remanejado":   student.get("remanejado", False)
        }
        # --- FIM DA CORREÇÃO ---
        
        data_to_insert_dict[inscricao] = new_row
            
    final_list = list(data_to_insert_dict.values())
    
    print(f"✅ {len(final_list)} registros únicos prontos para o upload. ({len(students_list) - len(final_list)} duplicatas removidas)")
    return final_list

def upload_data(supabase: Client, data: list):
    """
    Envia os dados em massa para o Supabase usando Upsert.
    """
    if not data:
        print("ℹ️ Nenhum dado para enviar. Encerrando.")
        return

    print(f"📦 Enviando {len(data)} registros para a tabela '{TABLE_NAME}'...")
    
    try:
        response = supabase.table(TABLE_NAME).upsert(
            data, 
            on_conflict="inscricao"
        ).execute()

        if response.data:
            print(f"🎉 Sucesso! {len(response.data)} registros inseridos/atualizados.")
        else:
            print("⚠️ Resposta do Supabase vazia, mas sem erros.")
            if hasattr(response, 'error') and response.error:
                 print(f"❌ Erro na API do Supabase: {response.error.message}")

    except Exception as e:
        print(f"❌ Erro fatal durante o upload: {e}", file=sys.stderr)
        # Imprime detalhes se for um erro da API do Supabase
        if hasattr(e, 'message'):
             print(f"   Detalhes: {e.message}", file=sys.stderr)

def main():
    """Função principal para orquestrar o script."""
    
    if len(sys.argv) < 2:
        print("❌ Erro: Você deve passar o nome do arquivo JSON como argumento.", file=sys.stderr)
        print("   Exemplo: python upload_script.py campinas.json", file=sys.stderr)
        sys.exit(1)
        
    json_file_to_upload = sys.argv[1]

    supabase_url, supabase_key = load_env_vars()
    supabase_client = connect_to_supabase(supabase_url, supabase_key)
    students_json_data = load_json_file(json_file_to_upload)
    data_for_db = transform_data(students_json_data) 
    
    upload_data(supabase_client, data_for_db)

if __name__ == "__main__":
    main()