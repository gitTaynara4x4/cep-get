from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import io
import pandas as pd
import os
import requests

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CACHE_PATH = "cache.json"
BITRIX_URL = "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5/"

# Caches locais
pipeline_cache = {}
fases_cache = {}

# ==================== Funções de integração Bitrix ====================

def obter_nome_pipeline(category_id):
    if category_id in pipeline_cache:
        return pipeline_cache[category_id]
    
    url = BITRIX_URL + "crm.category.list?entityTypeId=2"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get('result', [])
        for item in data:
            if str(item['ID']) == category_id:
                pipeline_cache[category_id] = item['NAME']
                print(f"✅ Pipeline {category_id} carregada dinamicamente: {item['NAME']}")
                return item['NAME']
    except Exception as e:
        print(f"Erro ao obter nome do pipeline {category_id}: {e}")

    return f"ID {category_id}"

def carregar_fases(category_id):
    global fases_cache
    url = BITRIX_URL + f"crm.dealcategory.stage.list?ID={category_id}"
    try:
        resp = requests.get(url)
        data = resp.json().get('result', [])
        fases_cache[str(category_id)] = {item['STATUS_ID']: item['NAME'] for item in data}
    except Exception as e:
        print(f"Erro ao carregar fases da categoria {category_id}: {e}")

def obter_deal_completa(deal_id):
    url = BITRIX_URL + f"crm.deal.get?id={deal_id}"
    try:
        resp = requests.get(url)
        data = resp.json().get('result', None)
        return data
    except Exception as e:
        print(f"Erro ao obter dados completos da deal {deal_id}: {e}")
        return None

# ==================== Funções principais ====================

def carregar_cache():
    if not os.path.exists(CACHE_PATH):
        return []
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️ ERRO: cache.json inválido ou corrompido.")
        return []

def carregar_pipelines():
    """Pré-carrega pipeline_cache e fases_cache com base no cache atual."""
    dados = carregar_cache()
    for deal in dados:
        category_id = str(deal.get("CATEGORY_ID", ""))
        if category_id:
            if category_id not in pipeline_cache:
                obter_nome_pipeline(category_id)
            if category_id not in fases_cache:
                carregar_fases(category_id)
    print("✅ Pipelines e fases pré-carregadas com sucesso.")

def processar_deal(deal):
    deal_id = deal.get("ID")
    deal_completa = obter_deal_completa(deal_id)
    
    if not deal_completa:
        print(f"⚠️ Não foi possível obter dados completos da deal {deal_id}, usando dados parciais.")
        deal_completa = deal

    c = (deal_completa.get("UF_CRM_1700661314351") or "").replace("-", "").strip()
    contato = deal_completa.get("UF_CRM_1698698407472")
    category_id = str(deal_completa.get("CATEGORY_ID", ""))
    stage_id = deal_completa.get("STAGE_ID", "")

    pipeline_name = obter_nome_pipeline(category_id)

    if category_id and category_id not in fases_cache:
        carregar_fases(category_id)

    fase_name = fases_cache.get(category_id, {}).get(stage_id, stage_id)

    return {
        "id_card": deal_completa.get("ID"),
        "cliente": deal_completa.get("TITLE"),
        "pipeline": pipeline_name,
        "fase": fase_name,
        "contato": contato,
        "cep": c,
        "criado_em": deal_completa.get("DATE_CREATE")
    }

def buscar_cep_unico(cep):
    cep = cep.replace("-", "").strip()
    dados = carregar_cache()
    resultados = []

    for deal in dados:
        c = (deal.get("UF_CRM_1700661314351") or "").replace("-", "").strip()
        if c == cep:
            resultados.append(processar_deal(deal))
    return resultados

def buscar_varios_ceps(lista_ceps):
    ceps_set = set(c.strip().replace("-", "") for c in lista_ceps if c.strip())
    dados = carregar_cache()
    resultados = []

    for deal in dados:
        c = (deal.get("UF_CRM_1700661314351") or "").replace("-", "").strip()
        if c in ceps_set:
            resultados.append(processar_deal(deal))
    return resultados

async def extrair_ceps_arquivo(arquivo: UploadFile):
    nome = arquivo.filename.lower()
    conteudo = await arquivo.read()
    ceps = []

    if nome.endswith('.txt'):
        ceps = conteudo.decode().splitlines()
    elif nome.endswith('.csv'):
        df = pd.read_csv(io.BytesIO(conteudo))
        for col in df.columns:
            if 'cep' in col.lower():
                ceps = df[col].astype(str).tolist()
                break
    elif nome.endswith('.xlsx'):
        df = pd.read_excel(io.BytesIO(conteudo))
        for col in df.columns:
            if 'cep' in col.lower():
                ceps = df[col].astype(str).tolist()
                break

    return ceps

# ==================== Rotas ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/buscar")
async def buscar(
    cep: str = Form(None),
    arquivo: UploadFile = File(None),
    formato: str = Form("txt")
):
    if arquivo and arquivo.filename != "":
        ceps = await extrair_ceps_arquivo(arquivo)
        resultados = buscar_varios_ceps(ceps)

        if formato == "xlsx":
            df = pd.DataFrame(resultados)
            caminho_saida = "resultado.xlsx"
            df.to_excel(caminho_saida, index=False)
            return FileResponse(
                caminho_saida,
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                filename="resultado.xlsx"
            )
        else:
            output = io.StringIO()
            for res in resultados:
                output.write(
                    f"ID: {res['id_card']} | Cliente: {res['cliente']} | Pipeline: {res['pipeline']} | Fase: {res['fase']} | CEP: {res['cep']} | Contato: {res['contato']} | Criado em: {res['criado_em']}\n"
                )
            output.seek(0)
            return PlainTextResponse(content=output.read(), media_type='text/plain')

    elif cep:
        resultados = buscar_cep_unico(cep)
        return JSONResponse(content={"total": len(resultados), "resultados": resultados})

    else:
        return JSONResponse(content={"error": "Nenhum CEP ou arquivo enviado."})

# ==================== Inicialização ====================

carregar_pipelines()
