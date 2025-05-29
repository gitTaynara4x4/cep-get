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
BITRIX_URL = "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5"

# Função: carregar cache protegido contra erro
def carregar_cache():
    if not os.path.exists(CACHE_PATH):
        return []
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️ ERRO: cache.json inválido ou corrompido.")
        return []

# Função: obter nome do pipeline
def obter_nome_pipeline(category_id):
    resp = requests.get(f"{BITRIX_URL}/crm.category.list")
    categorias = resp.json().get('result', [])
    for cat in categorias:
        if str(cat['ID']) == str(category_id):
            return cat['NAME']
    return f"Pipeline {category_id}"

# Função: obter nome da fase
def obter_nome_fase(category_id, stage_id):
    resp = requests.get(f"{BITRIX_URL}/crm.dealcategory.stage.list", params={"id": category_id})
    estagios = resp.json().get('result', [])
    for est in estagios:
        if est['STATUS_ID'] == stage_id:
            return est['NAME']
    return f"Fase {stage_id}"

# Função: buscar por um único CEP
def buscar_cep_unico(cep):
    cep = cep.replace("-", "").strip()
    dados = carregar_cache()
    resultados = []

    for deal in dados:
        c = (deal.get("UF_CRM_1700661314351") or "").replace("-", "").strip()
        contato = deal.get("UF_CRM_1698698407472")
        if c == cep:
            categoria_id = deal.get("CATEGORY_ID")
            stage_id = deal.get("STAGE_ID")

            nome_pipeline = obter_nome_pipeline(categoria_id)
            nome_fase = obter_nome_fase(categoria_id, stage_id)

            resultados.append({
                "id_card": deal.get("ID"),
                "cliente": deal.get("TITLE"),
                "pipeline": nome_pipeline,
                "fase": nome_fase,
                "contato": contato,
                "cep": c,
                "criado_em": deal.get("DATE_CREATE")
            })
    return resultados

# Função: buscar vários CEPs
def buscar_varios_ceps(lista_ceps):
    ceps_set = set(c.strip().replace("-", "") for c in lista_ceps if c.strip())
    dados = carregar_cache()
    resultados = []

    for deal in dados:
        c = (deal.get("UF_CRM_1700661314351") or "").replace("-", "").strip()
        contato = deal.get("UF_CRM_1698698407472")
        if c in ceps_set:
            categoria_id = deal.get("CATEGORY_ID")
            stage_id = deal.get("STAGE_ID")

            nome_pipeline = obter_nome_pipeline(categoria_id)
            nome_fase = obter_nome_fase(categoria_id, stage_id)

            resultados.append({
                "id_card": deal.get("ID"),
                "cliente": deal.get("TITLE"),
                "pipeline": nome_pipeline,
                "fase": nome_fase,
                "contato": contato,
                "cep": c,
                "criado_em": deal.get("DATE_CREATE")
            })
    return resultados

# Função: extrair CEPs de arquivo
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

# Página inicial
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Rota de busca
@app.post("/buscar")
async def buscar(
    cep: str = Form(None),
    arquivo: UploadFile = File(None),
    formato: str = Form("txt")  # novo parâmetro opcional para escolher formato
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
        else:  # padrão: txt
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
