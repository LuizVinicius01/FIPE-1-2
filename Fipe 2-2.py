import pandas as pd
import requests
from sqlalchemy import create_engine
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import date
import traceback
import urllib
from pathlib import Path  # Para salvar dinamicamente na pasta Downloads

def get_sql_server_connection_str():
    """Retorna a string de conexão com o banco de dados SQL Server."""
    user = 'rpa_bi'
    password = 'Rp@_B&_P@rvi'
    host = '10.0.10.243'
    port = '54949'
    database = 'stage'
    
    params = urllib.parse.quote_plus(
        f'DRIVER=ODBC Driver 17 for SQL Server;SERVER={host},{port};DATABASE={database};UID={user};PWD={password}')
    return f'mssql+pyodbc:///?odbc_connect={params}'

def consultar_api(codigo_fipe, max_tentativas=3):
    url = f"https://brasilapi.com.br/api/fipe/preco/v1/{codigo_fipe}"
    for tentativa in range(max_tentativas):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return [
                    {
                        "Fipe_Codigo": codigo_fipe,
                        "valor": dado.get("valor"),
                        "marca": dado.get("marca"),
                        "modelo": dado.get("modelo"),
                        "anoModelo": dado.get("anoModelo"),
                        "combustivel": dado.get("combustivel"),
                        "mesReferencia": dado.get("mesReferencia"),
                        "tipoVeiculo": dado.get("tipoVeiculo"),
                        "siglaCombustivel": dado.get("siglaCombustivel")
                    }
                    for dado in response.json()
                ]
            print(f"Erro ao consultar {codigo_fipe} - Tentativa {tentativa + 1}: {response.status_code}")
        except Exception:
            print(f"Erro no código {codigo_fipe} - Tentativa {tentativa + 1}: {traceback.format_exc()}")
        time.sleep(2 ** tentativa)
    return None

def FIPE():
    try:
        conn_str = get_sql_server_connection_str()
        engine = create_engine(conn_str)
        
        inicio_query = time.time()
        query = "SELECT DISTINCT CAST(Fipe_Id AS VARCHAR(MAX)) AS Fipe_Id FROM [stage].[camada0].[AutoAvaliar_AvaliacoesTotais]"
        df_fipe = pd.read_sql(query, engine)
        print(f"Tempo para carregar dados do banco com DISTINCT: {time.time() - inicio_query:.2f} segundos")
        
        lista_fipes = df_fipe['Fipe_Id'].dropna().tolist()
        
        inicio_api = time.time()
        resultados_finais = []
        codigos_falharam = []
        max_workers = min(10, len(lista_fipes))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(consultar_api, codigo): codigo for codigo in lista_fipes}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    resultados_finais.extend(result)
                else:
                    codigos_falharam.append(futures[future])
        
        print(f"Tempo para consumir API: {time.time() - inicio_api:.2f} segundos")
        
        if resultados_finais:
            df_resultados = pd.DataFrame(resultados_finais)
            df_resultados['data_atualizacao'] = date.today()
            print("Resultados obtidos da API:")
            print(df_resultados.head())
            
            inicio_insercao = time.time()
            df_resultados.to_sql("AutoAvaliar_Fipe_Resultados", engine, if_exists="replace", index=False, chunksize=1000)
            print(f"Tempo para inserir dados no banco: {time.time() - inicio_insercao:.2f} segundos")
            print("Dados inseridos na tabela 'AutoAvaliar_Fipe_Resultados'.")
        else:
            print("Nenhum dado foi obtido da API.")
        
        if codigos_falharam:
            codigos_validos = [codigo for codigo in codigos_falharam if isinstance(codigo, str) and codigo.strip()]
            if codigos_validos:
                print("Códigos que falharam na primeira tentativa:")
                print(codigos_validos)

                # ✅ Salvar arquivo na pasta Downloads do usuário atual
                downloads_path = Path.home() / "Downloads"
                file_path = downloads_path / "codigos_falharam.txt"

                with open(file_path, "w", encoding="utf-8") as file:
                    file.write("\n".join(codigos_validos))

                print(f"Arquivo salvo em: {file_path}")
            else:
                print("Nenhum código válido para salvar.")
    except Exception:
        print(f"Erro na função FIPE: {traceback.format_exc()}")

if __name__ == "__main__":
    FIPE()