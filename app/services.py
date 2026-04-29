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

# Configura o logger
logger = logging.getLogger(__name__)
load_dotenv()

# --- CONFIGURAÇÕES WHATSAPP ---
WPP_URL_COMPLETA = os.getenv('WPP_API_URL')
WPP_TOKEN = os.getenv("AUTHENTICATION_API_KEY")

# --- FUNÇÕES BLING ---

async def get_new_token():
    url = "https://www.bling.com.br/Api/v3/oauth/token"
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': settings.BLING_REFRESH_TOKEN
    }
    async with httpx.AsyncClient() as client:
        auth = (settings.BLING_CLIENT_ID, settings.BLING_CLIENT_SECRET)
        response = await client.post(url, data=data, auth=auth)
        if response.status_code == 200:
            new_data = response.json()
            settings.BLING_ACCESS_TOKEN = new_data['access_token']
            set_key(".env", "BLING_ACCESS_TOKEN", settings.BLING_ACCESS_TOKEN)
            if new_data.get('refresh_token'):
                set_key(".env", "BLING_REFRESH_TOKEN", new_data['refresh_token'])
            return settings.BLING_ACCESS_TOKEN
        return None

async def fetch_estoque_atual(id_produto: int):
    url = f"https://www.bling.com.br/Api/v3/estoques/saldos?idsProdutos[]={id_produto}"
    headers = {"Authorization": f"Bearer {settings.BLING_ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get("data", [])
            return data[0].get("saldoFisicoTotal", 0) if data else 0
        return 0

# --- FUNÇÃO PRINCIPAL DE PROCESSAMENTO ---

async def processar_venda_completa(id_nota: int):
    logger.debug(f"🔍 Iniciando processamento da nota: {id_nota}")
    url = f"https://www.bling.com.br/Api/v3/nfce/{id_nota}"
    headers = {"Authorization": f"Bearer {settings.BLING_ACCESS_TOKEN}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 401:
            token = await get_new_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                response = await client.get(url, headers=headers)

        if response.status_code == 200:
            venda = response.json().get("data", {})
            itens = venda.get("itens", [])
            logger.info(f"📦 Nota {id_nota} contém {len(itens)} itens.")
            
            db = SessionLocal()
            try:
                for item in itens:
                    id_prod = item.get("id") or item.get("produto", {}).get("id")
                    sku = item.get("codigo") or "S-SKU"
                    descricao = item.get("descricao")
                    valor = item.get("valor")
                    qtd = item.get("quantidade")
                    
                    estoque_restante = 0
                    if id_prod and sku != "AVULSO":
                        estoque_restante = await fetch_estoque_atual(id_prod)

                    dados_venda = {
                        "venda_id": id_nota,
                        "produto_id": id_prod,
                        "id_loja": venda.get("loja", {}).get("id", 0),
                        "sku": sku,
                        "nome_produto": descricao,
                        "valor_unitario": valor,
                        "quantidade": qtd,
                        "valor_total": valor * qtd,
                        "estoque_pos_venda": estoque_restante,
                        "timestamp": venda.get("dataEmissao")
                    }

                    stmt = insert(VendaItem).values(dados_venda)
                    stmt = stmt.on_conflict_do_update(
                        constraint="unique_venda_item",
                        set_=dados_venda
                    )
                    db.execute(stmt)
                
                db.commit()
                logger.info(f"✅ Nota {id_nota} processada!")
                
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Erro no banco: {e}")
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
        async with httpx.AsyncClient() as client:
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
        async with httpx.AsyncClient() as client:
            response = await client.post(url_media, data=payload, files=files, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"❌ Erro ao enviar Imagem Zap: {e}")
        return {"status": "error", "message": str(e)}

def gerar_relatorio_loja_automatizado(df_loja, nome_loja):
    """
    Gera o HTML e converte para PNG usando a lógica do Dashboard.
    """
    # === CÁLCULOS (IGUAL AO DASHBOARD) ===
    faturamento = df_loja['valor_total'].sum()
    vendas = df_loja['venda_id'].nunique()
    ticket = faturamento / vendas if vendas > 0 else 0
    
    # Projeção (ajuste conforme sua lógica de dias)
    dias_observados = df_loja["data"].nunique()
    projecao = (faturamento / dias_observados) * 6 if dias_observados > 0 else 0

    # === HTML + CSS (ESTILO EXAGERADO) ===
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0e1117; color: white; padding: 30px; }}
            .header {{ border-bottom: 2px solid #6B3FA0; padding-bottom: 10px; margin-bottom: 20px; }}
            .kpi-container {{ display: flex; justify-content: space-between; gap: 20px; margin-bottom: 30px; }}
            .kpi-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; flex: 1; text-align: center; }}
            .kpi-value {{ font-size: 24px; font-weight: bold; color: #6B3FA0; }}
            .kpi-label {{ font-size: 14px; color: #8b949e; margin-top: 5px; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #484f58; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏪 {nome_loja} - Relatório de Performance</h1>
        </div>
        
        <div class="kpi-container">
            <div class="kpi-card">
                <div class="kpi-value">R$ {faturamento:,.2f}</div>
                <div class="kpi-label">Faturamento Total</div>
                <div style="font-size: 11px; color: #3fb950;">Projeção: R$ {projecao:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{vendas}</div>
                <div class="kpi-label">Vendas Realizadas</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">R$ {ticket:,.2f}</div>
                <div class="kpi-label">Ticket Médio</div>
            </div>
        </div>

        <h3 style="color: #F59E0B;">📦 Top Produtos (Qtd)</h3>
        <table style="width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden;">
            <tr style="background: #30363d; text-align: left;">
                <th style="padding: 10px;">Produto</th>
                <th style="padding: 10px;">Qtd</th>
                <th style="padding: 10px;">Total</th>
            </tr>
            {"".join([f"<tr style='border-bottom: 1px solid #30363d;'><td style='padding: 10px;'>{row['nome_produto']}</td><td style='padding: 10px;'>{row['quantidade']}</td><td style='padding: 10px;'>R$ {row['valor_total']:,.2f}</td></tr>" 
                      for _, row in df_loja.groupby('nome_produto').agg({'quantidade':'sum', 'valor_total':'sum'}).sort_values('quantidade', ascending=False).head(5).iterrows()])}
        </table>

        <div class="footer">Gerado automaticamente pelo Sistema Exagerado Insights</div>
    </body>
    </html>
    """

    # === CONVERSÃO PARA PNG (PLAYWRIGHT) ===
    nome_arquivo = f"relatorio_{nome_loja.lower().replace(' ', '_')}.png"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 800, "height": 1000})
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=nome_arquivo, full_page=True)
        browser.close()

    return nome_arquivo