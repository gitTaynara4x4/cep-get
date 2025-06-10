from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
    FileResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import io
import pandas as pd
import psycopg2
import os
import tempfile
from dotenv import load_dotenv
import requests

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="./cep-get/static"), name="static")
templates = Jinja2Templates(directory="./cep-get/templates")


BITRIX_API_BASE = "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5"


def get_conn():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )


def get_categories():
    try:
        resp = requests.get(
            f"{BITRIX_API_BASE}/crm.category.list", params={"entityTypeId": 2}
        )
        data = resp.json()
        return {
            cat["id"]: cat["name"]
            for cat in data.get("result", {}).get("categories", [])
        }
    except:
        return {}


def get_stages(category_id):
    try:
        resp = requests.get(
            f"{BITRIX_API_BASE}/crm.dealcategory.stage.list", params={"id": category_id}
        )
        data = resp.json()
        return {stage["STATUS_ID"]: stage["NAME"] for stage in data.get("result", [])}
    except:
        return {}


def buscar_por_cep(cep):
    cep_limpo = cep.replace("-", "").strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "title", "stage_id", "category_id", "uf_crm_cep", "uf_crm_contato", "date_create", "contato01", "contato02", "ordem_de_servico", "nome_do_cliente",
            "nome_da_mae", "data_de_vencimento", "email", "cpf", "rg", "referencia", "rua", "data_de_instalacao", "quais_operadoras_tem_viabilidade"
                FROM deals
                WHERE replace("uf_crm_cep", '-', '') = %s;
            """,
                (cep_limpo,),
            )
            rows = cur.fetchall()

    # Carrega categorias e inicializa cache stages
    categorias = get_categories()
    stages_cache = {}

    resultados = []
    for r in rows:
        cat_id = r[3]
        categoria_nome = categorias.get(cat_id, str(cat_id))

        # Carrega estágios da categoria (cache)
        if cat_id not in stages_cache:
            stages_cache[cat_id] = get_stages(cat_id)
        fase_nome = stages_cache[cat_id].get(r[2], r[2])  # r[2] é stage_id

        resultados.append(
            {
                "id": r[0],
                "cliente": r[1],
                "fase": fase_nome,
                "categoria": categoria_nome,
                "cep": r[4],
                "contato": r[5],
                "criado_em": (
                    r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
                ),
                "contato01": r[8],
                "contato02": r[9],
                "ordem_de_servico": r[10],
                "nome_do_cliente": r[11],
                "nome_da_mae": r[12],
                "data_de_vencimento": r[13],
                "email": r[14],
                "cpf": r[15],
                "rg": r[16],
                "referencia": r[17],
                "rua": r[18],
                "data_de_instalacao": r[19],
                "quais_operadoras_tem_viabilidade": r[20],
            }
        )
    return resultados


def buscar_varios_ceps(lista_ceps):
    ceps_limpos = [c.replace("-", "").strip() for c in lista_ceps if c.strip()]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "title", "stage_id", "category_id", "uf_crm_cep", "uf_crm_contato", "date_create", "contato01", "contato02", "ordem_de_servico", "nome_do_cliente",
            "nome_da_mae", "data_de_vencimento", "email", "cpf", "rg", "referencia", "rua", "data_de_instalacao", "quais_operadoras_tem_viabilidade"
                FROM deals
                WHERE replace("uf_crm_cep", '-', '') = ANY(%s);
            """,
                (ceps_limpos),
            )
            rows = cur.fetchall()

    categorias = get_categories()
    stages_cache = {}

    resultados = []
    for r in rows:
        cat_id = r[3]
        categoria_nome = categorias.get(cat_id, str(cat_id))

        if cat_id not in stages_cache:
            stages_cache[cat_id] = get_stages(cat_id)
        fase_nome = stages_cache[cat_id].get(r[2], r[2])

        resultados.append(
            {
                "id": r[0],
                "cliente": r[1],
                "fase": fase_nome,
                "categoria": categoria_nome,
                "uf_crm_cep": r[4],
                "contato": r[5],
                "criado_em": (
                    r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
                ),
                "contato01": r[8],
                "contato02": r[9],
                "ordem_de_servico": r[10],
                "nome_do_cliente": r[11],
                "nome_da_mae": r[12],
                "data_de_vencimento": r[13],
                "email": r[14],
                "cpf": r[15],
                "rg": r[16],
                "referencia": r[17],
                "rua": r[18],
                "data_de_instalacao": r[19],
                "quais_operadoras_tem_viabilidade": r[20],
            }
        )
    return resultados


async def extrair_ceps_arquivo(arquivo: UploadFile):
    nome = arquivo.filename.lower()
    conteudo = await arquivo.read()
    ceps = []

    if nome.endswith(".txt"):
        ceps = conteudo.decode().splitlines()
    elif nome.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(conteudo))
        for col in df.columns:
            if "cep" in col.lower():
                ceps = df[col].astype(str).tolist()
                break
    elif nome.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(conteudo))
        for col in df.columns:
            if "cep" in col.lower():
                ceps = df[col].astype(str).tolist()
                break
    return ceps


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/buscar")
async def buscar(
    cep: str = Form(None), arquivo: UploadFile = File(None), formato: str = Form("txt")
):
    if cep and (arquivo and arquivo.filename != ""):
        return JSONResponse(
            content={"error": "Envie apenas um CEP ou um arquivo, não ambos."},
            status_code=400,
        )

    if arquivo and arquivo.filename != "":
        ceps = await extrair_ceps_arquivo(arquivo)
        if not ceps:
            return JSONResponse(
                content={"error": "Nenhum CEP encontrado no arquivo."}, status_code=400
            )

        resultados = buscar_varios_ceps(ceps)
        if not resultados:
            resultados = []

        if formato == "xlsx":
            df = pd.DataFrame(resultados)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                df.to_excel(tmp.name, index=False)
                tmp.seek(0)
                return FileResponse(
                    tmp.name,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename="resultado.xlsx",
                )
        else:
            output = io.StringIO()
            for res in resultados:
                output.write(
                    f"ID: {res['id']} | Cliente: {res['cliente']} | Fase: {res['fase']} | Categoria: {res['categoria']} | CEP: {res['uf_crm_cep']} | Contato: {res['contato']} | \
                          Criado em: {res['criado_em']} | Contato 01: {res['contato01']} | Contato 02: {res['contato02']} | Ordem de Serviço: {res['ordem_de_servico']} \
                             | Nome do Cliente: {res['nome_do_cliente']} | Nome da Mãe: {res['nome_da_mae']} | Data de Vencimento: {res['data_de_vencimento']} | Email: {res['email']} \
                                 | CPF: {res['cpf']} | RG: {res['rg']} | Referência: {res['referencia']} | Rua: {res['rua']} | Data de Instalação: {res['data_de_instalacao']} | Quais operadoras tem viabilidade: {res['quais_operadoras_tem_viabilidade']} \n"
                )
            output.seek(0)

            headers = {"Content-Disposition": 'attachment; filename="resultado.txt"'}

            return StreamingResponse(output, media_type="text/plain", headers=headers)

    elif cep:
        resultados = buscar_por_cep(cep)
        if not resultados:
            resultados = []
        return JSONResponse(
            content={"total": len(resultados), "resultados": resultados}
        )

    else:
        return JSONResponse(
            content={"error": "Nenhum CEP ou arquivo enviado."}, status_code=400
        )
