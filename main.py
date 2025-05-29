from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
import pandas as pd
import io

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Constantes da API Bitrix
BITRIX_API_URL = "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5"

# ✅ Função para mapear categoryId → nome
def get_category_map():
    url = f"{BITRIX_API_URL}/crm.category.list?entityTypeId=2"
    response = requests.get(url)
    categorias = response.json().get('result', {}).get('categories', [])
    return {int(c['id']): c['name'] for c in categorias}

category_map = get_category_map()

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/buscar")
async def buscar(cep: str = Form(None), arquivo: UploadFile = File(None), formato: str = Form(...)):
    ceps = []

    if cep:
        ceps.append(cep)
    elif arquivo:
        contents = await arquivo.read()
        if arquivo.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        elif arquivo.filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(contents))
        else:  # txt
            df = pd.read_csv(io.StringIO(contents.decode('utf-8')), header=None)
            df.columns = ['cep']
        ceps = df['cep'].astype(str).tolist()

    resultados = []

    for c in ceps:
        # ✅ Buscar negócios com esse CEP
        url = f"{BITRIX_API_URL}/crm.deal.list"
        params = {
            "filter[UF_CRM_1690812630]": c,  # Ajuste esse campo se necessário
            "select[]": "ID",
            "select[]": "TITLE",
            "select[]": "STAGE_ID",
            "select[]": "CATEGORY_ID",
            "select[]": "DATE_CREATE",
            "select[]": "UF_CRM_1690812630",  # Campo do CEP
            "select[]": "CONTACT_ID"
        }
        response = requests.get(url, params=params)
        data = response.json()

        if data.get("result"):
            for deal in data["result"]:
                category_id = int(deal.get("CATEGORY_ID", 0))
                category_name = category_map.get(category_id, f"ID {category_id}")

                resultado = {
                    "id_card": deal.get("ID"),
                    "cliente": deal.get("TITLE"),
                    "pipeline": category_name,
                    "fase": deal.get("STAGE_ID"),
                    "contato": deal.get("CONTACT_ID"),
                    "cep": c,
                    "criado_em": deal.get("DATE_CREATE")
                }
                resultados.append(resultado)

    if formato == "txt":
        output = io.StringIO()
        for r in resultados:
            output.write(f"ID: {r['id_card']}\n")
            output.write(f"Cliente: {r['cliente']}\n")
            output.write(f"Pipeline: {r['pipeline']}\n")
            output.write(f"Fase: {r['fase']}\n")
            output.write(f"Contato: {r['contato']}\n")
            output.write(f"CEP: {r['cep']}\n")
            output.write(f"Criado em: {r['criado_em']}\n")
            output.write("-" * 40 + "\n")
        output.seek(0)
        return StreamingResponse(io.BytesIO(output.getvalue().encode()), media_type="text/plain", headers={"Content-Disposition": "attachment; filename=resultados.txt"})

    elif formato == "xlsx":
        df = pd.DataFrame(resultados)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=resultados.xlsx"})

    return JSONResponse(content={"resultados": resultados})
