import httpx
import logging
import os
from dotenv import load_dotenv, set_key
from sqlalchemy.dialects.postgresql import insert

from config import settings
from database import SessionLocal
from models import VendaItem
import pandas as pd
import plotly.express as px
from playwright.sync_api import sync_playwright
import base64
import json
import asyncio
# Configura o logger
logger = logging.getLogger(__name__)
load_dotenv()

# --- CONFIGURAÇÕES WHATSAPP ---
WPP_URL_COMPLETA = os.getenv('WPP_API_URL')
WPP_TOKEN = os.getenv("AUTHENTICATION_API_KEY")

# --- FUNÇÕES BLING ---

TOKEN_FILE = "/data/bling_tokens.json"

def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        data = {
            "access_token": settings.BLING_ACCESS_TOKEN,
            "refresh_token": settings.BLING_REFRESH_TOKEN
        }
        with open(TOKEN_FILE, "w") as f:
            json.dump(data, f)
        return data
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def save_tokens(access_token, refresh_token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": access_token,
            "refresh_token": refresh_token
        }, f)

token_lock = asyncio.Lock()

async def get_new_token():
    async with token_lock:
        tokens = load_tokens()

        url = "https://www.bling.com.br/Api/v3/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"]
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            auth = (settings.BLING_CLIENT_ID, settings.BLING_CLIENT_SECRET)
            response = await client.post(url, data=data, auth=auth)

            if response.status_code != 200:
                raise Exception(f"Erro ao renovar token: {response.text}")

            new_data = response.json()

            access_token = new_data["access_token"]
            refresh_token = new_data.get("refresh_token", tokens["refresh_token"])

            save_tokens(access_token, refresh_token)

            return access_token

async def fetch_estoque_atual(sku: str):
    url = f"https://www.bling.com.br/Api/v3/estoques/saldos?codigos[]={sku}"
    
    tokens = load_tokens()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        for tentativa in range(3):
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json().get("data", [])
                return data[0].get("saldoFisicoTotal", 0) if data else 0

            if response.status_code == 429:
                await asyncio.sleep(2 ** tentativa)
                continue

            break

    return None  # melhor que 0, pra saber que falhou

# --- FUNÇÃO PRINCIPAL DE PROCESSAMENTO ---

async def processar_venda_completa(id_nota: int):
    logger.debug(f"🔍 Iniciando processamento da nota: {id_nota}")
    url = f"https://www.bling.com.br/Api/v3/nfce/{id_nota}"
    tokens = load_tokens()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)

        if response.status_code == 401:
            tokens = load_tokens()
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
            response = await client.get(url, headers=headers)
            if response.status_code == 401:
                token = await get_new_token()
                headers["Authorization"] = f"Bearer {token}"
                response = await client.get(url, headers=headers)

        if response.status_code == 404:
            raise Exception("NOTA_NAO_ENCONTRADA")
        if response.status_code == 429:
            raise Exception("RATE_LIMIT")
        if response.status_code != 200:
            raise Exception(f"Erro HTTP {response.status_code}: {response.text}")

        venda = response.json().get("data", {})
        itens = venda.get("itens", [])
        logger.info(f"📦 Nota {id_nota} contém {len(itens)} itens.")

        # ← UMA conexão pra nota inteira
        db = SessionLocal()
        try:
            for linha, item in enumerate(itens):
                sku = item.get("codigo") or "S-SKU"
                dados_venda = {
                    "venda_id": id_nota,
                    "produto_id": sku,
                    "id_loja": venda.get("loja", {}).get("id", 0),
                    "sku": sku,
                    "linha": linha,
                    "nome_produto": item.get("descricao"),
                    "valor_unitario": item.get("valor"),
                    "quantidade": item.get("quantidade"),
                    "valor_total": item.get("valor") * item.get("quantidade"),
                    "estoque_pos_venda": None,
                    "timestamp": venda.get("dataEmissao")
                }
                stmt = insert(VendaItem).values(dados_venda)
                stmt = stmt.on_conflict_do_update(
                    constraint="unique_venda_item",
                    set_=dados_venda
                )
                db.execute(stmt)

            db.commit()  # ← um commit pra nota inteira
            logger.info(f"✅ Nota {id_nota} processada!")

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Erro nota {id_nota}: {e}")
            raise  # ← propaga pro worker tratar
        finally:
            db.close()

# --- FUNÇÃO WHATSAPP ---

async def enviar_mensagem_whatsapp(numero: str, texto: str):
    """
    Envia uma mensagem de texto usando a URL completa definida no .env
    """
    headers = {
        "apikey": WPP_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "number": numero,
        "text": texto,
        "delay": 1200,
        "linkPreview": True
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(WPP_URL_COMPLETA, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"❌ Erro ao enviar WhatsApp: {e}")
        return {"status": "error", "message": str(e)}
    
    
async def enviar_imagem_whatsapp(numero: str, caption: str, file_content: bytes, file_name: str):
    """
    Envia uma imagem (PNG/JPG) via Evolution API.
    """
    url_media = WPP_URL_COMPLETA.replace("sendText", "sendMedia")
    
    headers = {"apikey": WPP_TOKEN}
    
    files = {
        "file": (file_name, file_content, "image/png")
    }
    
    payload = {
        "number": numero,
        "mediatype": "image",
        "caption": caption
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url_media, data=payload, files=files, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"❌ Erro ao enviar Imagem Zap: {e}")
        return {"status": "error", "message": str(e)}

def gerar_html_secao_loja(df_loja, nome_loja, loja_id, meta_map):

    import pandas as pd
    import plotly.express as px

    # =========================
    # SEGURANÇA
    # =========================
    if df_loja is None or df_loja.empty:
        return """
        <html>
        <body style="font-family:sans-serif;padding:20px;">
            <h3>Sem dados disponíveis para essa loja</h3>
        </body>
        </html>
        """

    # =========================
    # KPI BASE
    # =========================
    faturamento = df_loja['valor_total'].sum()
    vendas = df_loja['venda_id'].nunique()
    ticket = faturamento / vendas if vendas > 0 else 0

    # =========================
    # PROJEÇÃO
    # =========================
    dias = df_loja["data"].nunique()
    dias_totais = 6

    projecao = (faturamento / dias) * dias_totais if dias > 0 else 0

    # =========================
    # META
    # =========================
    meta_loja = meta_map.get(loja_id, 0)

    atingimento = (faturamento / meta_loja * 100) if meta_loja > 0 else 0
    atingimento_proj = (projecao / meta_loja * 100) if meta_loja > 0 else 0

    if meta_loja == 0:
        status_meta = "Sem meta definida"
        cor_status = "#6B7280"
    elif atingimento >= 100:
        status_meta = "🔥 Meta atingida"
        cor_status = "#10B981"
    elif atingimento_proj >= 100:
        status_meta = "📈 Deve atingir a meta"
        cor_status = "#F59E0B"
    else:
        status_meta = "⚠️ Abaixo da meta"
        cor_status = "#EF4444"

    # =========================
    # HORAS
    # =========================
    faturamento_hora = (
        df_loja.groupby('hora')['valor_total']
        .sum()
        .reset_index()
        .sort_values("hora")
    )

    if not faturamento_hora.empty:
        melhor_hora = faturamento_hora.loc[faturamento_hora['valor_total'].idxmax(), 'hora']
        pior_hora = faturamento_hora.loc[faturamento_hora['valor_total'].idxmin(), 'hora']

        ultima_hora = faturamento_hora.iloc[-1]['hora']
        valor_ultima_hora = faturamento_hora.iloc[-1]['valor_total']
        media_hora = faturamento_hora['valor_total'].mean()

        pico = faturamento_hora['valor_total'].max()
        vale = faturamento_hora['valor_total'].min()

        status_hora = "🔥 Acima da média" if valor_ultima_hora >= media_hora else "⚠️ Abaixo da média"
    else:
        melhor_hora = pior_hora = ultima_hora = "-"
        valor_ultima_hora = pico = vale = 0
        status_hora = "Sem dados"

    # =========================
    # GRÁFICO (DIÁRIO)
    # =========================
    faturamento_dia = (
        df_loja.groupby('data')['valor_total']
        .sum()
        .reset_index()
        .sort_values("data")
    )

    faturamento_dia["data"] = pd.to_datetime(faturamento_dia["data"])
    faturamento_dia["data_str"] = faturamento_dia["data"].dt.strftime("%d/%m")

    fig = px.line(
        faturamento_dia,
        x='data_str',
        y='valor_total',
        markers=True
    )

    fig.update_traces(line=dict(color="#6B3FA0", width=3))

    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(0,0,0,0.05)')
    )

    grafico_html = fig.to_html(full_html=False, include_plotlyjs='cdn')

    # =========================
    # TOP PRODUTOS
    # =========================

    # FATURAMENTO
    top_fat = (
        df_loja.groupby('nome_produto')['valor_total']
        .sum()
        .sort_values(ascending=False)
        .head(3)
        .reset_index()
    )

    lista_fat = "".join([
        f"<li><b>{row['nome_produto']}</b> — R$ {row['valor_total']:,.2f}</li>"
        for _, row in top_fat.iterrows()
    ])

    # QUANTIDADE
    top_qtd = (
        df_loja.groupby('nome_produto')['quantidade']
        .sum()
        .sort_values(ascending=False)
        .head(3)
        .reset_index()
    )

    lista_qtd = "".join([
        f"<li><b>{row['nome_produto']}</b> — {int(row['quantidade'])} un</li>"
        for _, row in top_qtd.iterrows()
    ])

    # RECENTE
    ultimas_horas = faturamento_hora.tail(2)['hora'].tolist() if not faturamento_hora.empty else []

    df_recente = df_loja[df_loja['hora'].isin(ultimas_horas)]

    top_recente = (
        df_recente.groupby('nome_produto')['valor_total']
        .sum()
        .sort_values(ascending=False)
        .head(3)
        .reset_index()
    )

    if top_recente.empty:
        lista_recente = "<li>Sem vendas recentes</li>"
    else:
        lista_recente = "".join([
            f"<li><b>{row['nome_produto']}</b> — R$ {row['valor_total']:,.2f}</li>"
            for _, row in top_recente.iterrows()
        ])

    # =========================
    # HTML FINAL
    # =========================
    html = f"""
    <html>
    <body style="font-family:sans-serif;background:#F6F4EE;padding:20px;">

        <div style="max-width:520px;margin:auto;">

            <!-- HEADER -->
            <div style="background:#6B3FA0;color:white;padding:16px;border-radius:12px;">
                <h2 style="margin:0;">🏪 {nome_loja}</h2>
                <p style="margin:4px 0 0 0;font-size:12px;">
                    Atualizado às {pd.Timestamp.now().strftime('%H:%M')}
                </p>
            </div>

            <!-- KPI -->
            <div style="background:white;padding:16px;border-radius:12px;margin-top:12px;">

                <p><b>💰 Faturamento:</b> R$ {faturamento:,.2f}</p>
                <p><b>🧾 Vendas:</b> {vendas}</p>
                <p><b>🎯 Ticket:</b> R$ {ticket:,.2f}</p>

                <hr>

                <p><b>🎯 Meta:</b> R$ {meta_loja:,.2f}</p>

                <p style="color:{cor_status};font-weight:bold;font-size:16px;">
                    📊 {atingimento:.0f}% da meta
                </p>

                <p style="color:#6B7280;">
                    🔮 Projeção: R$ {projecao:,.2f} ({atingimento_proj:.0f}%)
                </p>

                <p style="color:{cor_status};font-weight:bold;">
                    {status_meta}
                </p>

            </div>

            <!-- MOMENTO -->
            <div style="background:white;padding:16px;border-radius:12px;margin-top:12px;">

                <b>⏱ Agora</b>

                <p><b>Última hora:</b> {ultima_hora}h — R$ {valor_ultima_hora:,.2f}</p>

                <p style="color:{'#10B981' if 'Acima' in status_hora else '#EF4444'};">
                    {status_hora}
                </p>

            </div>

            <!-- INSIGHTS -->
            <div style="background:white;padding:16px;border-radius:12px;margin-top:12px;">

                <b>📌 Insights</b>

                <p>🔥 Melhor hora: {melhor_hora}h (R$ {pico:,.2f})</p>
                <p>⚠️ Pior hora: {pior_hora}h (R$ {vale:,.2f})</p>

            </div>

            <!-- GRÁFICO -->
            <div style="background:white;padding:16px;border-radius:12px;margin-top:12px;">
                {grafico_html}
            </div>

            <!-- PRODUTOS -->
            <div style="background:white;padding:16px;border-radius:12px;margin-top:12px;">

                <b>🔥 Vendendo Agora</b>
                <ul>{lista_recente}</ul>

                <hr>

                <b>🏆 Top Faturamento</b>
                <ul>{lista_fat}</ul>

                <hr>

                <b>📦 Mais Vendidos</b>
                <ul>{lista_qtd}</ul>

            </div>

        </div>

    </body>
    </html>
    """

    return html

def gerar_relatorio_loja_automatizado(df_loja, nome_loja, loja_id, meta_map):
    """
    Gera o HTML e converte para PNG usando a lógica do Dashboard.
    """
    html_content = gerar_html_secao_loja(df_loja, nome_loja, loja_id, meta_map)

    # === CONVERSÃO PARA PNG (PLAYWRIGHT) ===
    nome_arquivo = f"relatorio_{nome_loja.lower().replace(' ', '_')}.png"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 800, "height": 1000})
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=nome_arquivo, full_page=True)
        browser.close()

    return nome_arquivo