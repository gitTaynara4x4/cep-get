import psycopg2
import requests
import time
import os

from dotenv import load_dotenv

load_dotenv()

# Parâmetros banco
DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

WEBHOOKS = [
    "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5/crm.deal.list",
    "https://marketingsolucoes.bitrix24.com.br/rest/5332/y5q6wd4evy5o57ze/crm.deal.list",
]

# Webhooks para pegar categorias e estágios
WEBHOOK_CATEGORIES = [
    "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5/crm.dealcategory.list",
    "https://marketingsolucoes.bitrix24.com.br/rest/5332/y5q6wd4evy5o57ze/crm.dealcategory.list",
]

WEBHOOK_STAGES = [
    "https://marketingsolucoes.bitrix24.com.br/rest/5332/8zyo7yj1ry4k59b5/crm.dealcategory.stage.list",
    "https://marketingsolucoes.bitrix24.com.br/rest/5332/y5q6wd4evy5o57ze/crm.dealcategory.stage.list",
]


operador_map = {
    "132": "VERO",
    "34652": "GIGA+",
    "48734": "BLINK",
    "48764": "DESKTOP",
    "49750": "MASTER",
    "60994": "BL FIBRA",
    "61062": "IMPLANTAR",
    "61156": "CDB",
    "61158": "NIO",
    "356": "NENHUMA OPERADORA",
    "352": "NÃO INFORMOU ENDEREÇO",
}


PARAMS = {
    "select[]": [
        "ID",
        "TITLE",
        "STAGE_ID",
        "CATEGORY_ID",
        "OPPORTUNITY",
        "CONTACT_ID",
        "BEGINDATE",
        "SOURCE_ID",
        "UF_CRM_1700661314351",  # CEP
        "UF_CRM_1698698407472",  # Contato 01
        "UF_CRM_1698698858832",  # Contato 02
        "UF_CRM_1697653896576",  # Ordem de serviço
        "UF_CRM_1697762313423",  # Nome do cliente / Razão social
        "UF_CRM_1697763267151",  # Nome da Mãe
        "UF_CRM_1697764091406",  # Data de vencimento
        "UF_CRM_1697807340141",  # E-mail
        "UF_CRM_1697807353336",  # CPF / CNPJ
        "UF_CRM_1697807372536",  # RG
        "UF_CRM_1697808018193",  # Referência
        "UF_CRM_1698688252221",  # Rua
        "UF_CRM_1698761151613",  # Data de instalação
        "UF_CRM_1699452141037",  # Quais operadoras tem viabilidade?
        "DATE_CREATE",
    ],
    "filter[>=DATE_CREATE]": "2021-01-01",
    "start": 0,
}

MAX_RETRIES = 20
RETRY_DELAY = 30
REQUEST_DELAY = 2
PAGE_DELAY = 30
LIMITE_REGISTROS_TURBO = 20000


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def upsert_deal(conn, deal):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO deals ("id", "title", "stage_id", "category_id", "uf_crm_cep", "uf_crm_contato", "date_create", "contato01", "contato02", "ordem_de_servico", "nome_do_cliente",
            "nome_da_mae", "data_de_vencimento", "email", "cpf", "rg", "referencia", "rua", "data_de_instalacao", "quais_operadoras_tem_viabilidade")
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ("id") DO UPDATE SET
                "title" = EXCLUDED."title",
                "stage_id" = EXCLUDED."stage_id",
                "category_id" = EXCLUDED."category_id",
                "uf_crm_cep" = EXCLUDED."uf_crm_cep",
                "uf_crm_contato" = EXCLUDED."uf_crm_contato",
                "date_create" = EXCLUDED."date_create";
                "contato01" = EXCLUDED."contato01";
                "contato02" = EXCLUDED."contato02";
                "ordem_de_servico" = EXCLUDED."ordem_de_servico";
                "nome_do_cliente" = EXCLUDED."nome_do_cliente";
                "nome_da_mae" = EXCLUDED."nome_da_mae";
                "data_de_vencimento" = EXCLUDED."data_de_vencimento";
                "email" = EXCLUDED."email";
                "cpf" = EXCLUDED."cpf";
                "rg" = EXCLUDED."rg";
                "referencia" = EXCLUDED."referencia";
                "rua" = EXCLUDED."rua";
                "data_de_instalacao" = EXCLUDED."data_de_instalacao";
                "quais_operadoras_tem_viabilidade" = EXCLUDED."quais_operadoras_tem_viabilidade";
        """,
            (
                deal.get("ID"),
                deal.get("TITLE"),
                deal.get("STAGE_ID"),
                deal.get("CATEGORY_ID"),
                deal.get("UF_CRM_1700661314351"),
                deal.get("UF_CRM_1698698407472"),
                deal.get("DATE_CREATE"),
                deal.get("cep"),
                deal.get("contato01"),
                deal.get("contato02"),
                deal.get("ordem_de_servico"),
                deal.get("nome_do_cliente"),
                deal.get("nome_da_mae"),
                deal.get("data_de_vencimento"),
                deal.get("email"),
                deal.get("cpf"),
                deal.get("rg"),
                deal.get("referencia"),
                deal.get("rua"),
                deal.get("data_de_instalacao"),
                deal.get("quais_operadoras_tem_viabilidade"),
            ),
        )


def fazer_requisicao(webhooks, params):
    for webhook in webhooks:
        try:
            resp = requests.get(webhook, params=params, timeout=30)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 1))
                print(
                    f"⏳ Limite de requisições atingido: aguardando {retry_after}s..."
                )
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            print(f"✅ Sucesso com {webhook}")
            return resp.json()
        except Exception as e:
            print(f"❌ Erro com {webhook}: {e}")
            continue
    print("🚫 Todos os webhooks falharam.")
    return None


def get_categories():
    params = {"start": 0}
    categories = {}
    while True:
        data = fazer_requisicao(WEBHOOK_CATEGORIES, params)
        if data is None:
            break
        for cat in data.get("result", []):
            categories[cat["ID"]] = cat["NAME"]
        if "next" in data and data["next"]:
            params["start"] = data["next"]
        else:
            break
    return categories


def get_stages(category_id):
    params = {"id": category_id, "start": 0}
    stages = {}
    while True:
        data = fazer_requisicao(WEBHOOK_STAGES, params)
        if data is None:
            print(f"🚫 Falha ao obter estágios para categoria {category_id}")
            break

        stages_list = data.get("result", [])
        for stage in stages_list:
            stages[stage["STATUS_ID"]] = stage["NAME"]

        if "next" in data and data["next"]:
            params["start"] = data["next"]
        else:
            break
    return stages


def baixar_todos_dados():
    conn = get_conn()
    conn.autocommit = False
    todos = []
    local_params = PARAMS.copy()
    tentativas = 0

    print("🚀 Buscando categorias para mapear nomes...")
    categorias = get_categories()

    print("🚀 Buscando estágios para todas as categorias...")
    estagios_por_categoria = {}
    for cat_id in categorias.keys():
        estagios_por_categoria[cat_id] = get_stages(cat_id)

    while True:
        print(
            f"📡 Requisição start={local_params['start']} | Total acumulado: {len(todos)}"
        )
        data = fazer_requisicao(WEBHOOKS, local_params)
        if data is None:
            tentativas += 1
            if tentativas >= MAX_RETRIES:
                print("🚫 Máximo de tentativas. Abortando.")
                break
            print(f"⏳ Retentativa {tentativas}/{MAX_RETRIES} em {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
            continue

        tentativas = 0
        deals = data.get("result", [])

        # Substituir IDs por nomes antes de salvar:
        for deal in deals:
            cat_id = deal.get("CATEGORY_ID")
            stage_id = deal.get("STAGE_ID")
            # Substitui categoria pelo nome, se existir
            if cat_id in categorias:
                deal["CATEGORY_ID"] = categorias[cat_id]
            # Substitui estágio pelo nome, se existir
            if (
                cat_id in estagios_por_categoria
                and stage_id in estagios_por_categoria[cat_id]
            ):
                deal["STAGE_ID"] = estagios_por_categoria[cat_id][stage_id]

            upsert_deal(conn, deal)

        todos.extend(deals)
        conn.commit()
        print(f"💾 Processados {len(deals)} registros.")

        if "next" in data and data["next"]:
            local_params["start"] = data["next"]
            time.sleep(
                PAGE_DELAY if len(todos) >= LIMITE_REGISTROS_TURBO else REQUEST_DELAY
            )
        else:
            print("🏁 Fim da paginação.")
            break

    conn.close()
    return todos


if __name__ == "__main__":
    print("🚀 Iniciando atualização dos deals...")
    baixar_todos_dados()
    print("✅ Deals atualizados.")
