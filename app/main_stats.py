import time
import pandas as pd
import logging
from datetime import datetime, timedelta
import asyncio
import os
from dotenv import load_dotenv

# Importações internas
from app.database import engine
from app.statistics import AlertaPerformance, AlertaRanking, AlertaLogistica, AlertaBayes
from services import enviar_mensagem_whatsapp, gerar_relatorio_loja_automatizado, enviar_imagem_whatsapp

# Configurações
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOJAS_ATIVAS = [205709335, 205709338, 205785185, 206057004, 205613392, 205406209, 206057013, 206057007] 
MAP_LOJAS_WPP = {
    205709335: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_KENNYON"), 
        os.getenv("WPP_NUMBER_ISAAC")
    ],
    205709338: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_HENRIQUE"),
        os.getenv("WPP_NUMBER_ISAAC") 
    ],
    205785185: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_GRAZI"),
        os.getenv("WPP_NUMBER_ISAAC") 
    ],
    206057004: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_SAMILA"),
        os.getenv("WPP_NUMBER_ISAAC") 
    ],
    205613392: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_CARLOS"),
        os.getenv("WPP_NUMBER_ISAAC")
    ],
    205406209: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_DON"),
        os.getenv("WPP_NUMBER_ISAAC")
    ],
    206057013: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_MALU"),
        os.getenv("WPP_NUMBER_ISAAC")
    ],
    206057007: [
        os.getenv("WPP_NUMBER_KAUA"), 
        os.getenv("WPP_NUMBER_GUSTAVO"),
        os.getenv("WPP_NUMBER_ISAAC") 
    ]
}

map_lojas = {
    205709335: "Vans",
    205709338: "Arezzo",
    205785185: "Off Premium",
    206057004: "Ida",
    205613392: "Aramis",
    205406209: "High",
    206057013: "Vix",
    206057007: "Surto dos 50"
}

meta_map = {
    205709335: 250000,  # Meta de vendas para a loja Vans
    205709338: 300000,  # Meta de vendas para a loja Arezzo
    205785185: 600000,  # Meta de vendas para a loja Off Premium
    206057004: 400000,   # Meta de vendas para a loja Ida
    205613392: 300000,  # Meta de vendas para a loja Aramis
    205406209: 150000,   # Meta de vendas para a loja High
    206057013: 150000,   # Meta de vendas para a loja Vix
    206057007: 30000   # Meta de vendas para a loja Surto dos 50
}

def rodar_pipeline_completo(enviar_print=False):
    agora = datetime.now()
    logger.info(f"🕒 Executando Pipeline - {'TEXTO + PRINT' if enviar_print else 'APENAS TEXTO'}")
    
    try:
        # Puxamos os últimos 7 dias para ter base comparativa e projeção
        query = "SELECT * FROM vendas_itens WHERE timestamp > now() - interval '7 days'"
        df_geral = pd.read_sql(query, engine)
        df_geral['timestamp'] = pd.to_datetime(df_geral['timestamp'])
        df_geral['data'] = df_geral['timestamp'].dt.date
        df_geral['hora'] = df_geral['timestamp'].dt.hour
    except Exception as e:
        logger.error(f"❌ Erro ao acessar banco: {e}")
        return

    if df_geral.empty:
        logger.warning("⚠️ Sem dados para análise.")
        return

    for loja_id in LOJAS_ATIVAS:
        df_loja = df_geral[df_geral['id_loja'] == loja_id]
        numero_destino = MAP_LOJAS_WPP.get(loja_id, [])
        
        if df_loja.empty or not numero_destino:
            continue

        for numero in numero_destino:

            # --- 1. INSIGHTS DE TEXTO (Sempre que o pipeline rodar) ---
            processadores = [
                AlertaPerformance(df_loja, loja_id),
                AlertaRanking(df_loja, loja_id),
                AlertaLogistica(df_loja, loja_id),
                AlertaBayes(df_loja, loja_id)
            ]
            nome_loja = map_lojas.get(loja_id)

            relatorio_texto = []
            for p in processadores:
                try:
                    p.analisar()
                    texto = p.gerar_texto()
                    if texto: relatorio_texto.append(texto)
                except Exception as e:
                    logger.error(f"❌ Erro no {p.__class__.__name__}: {e}")

            if relatorio_texto:
                cabecalho = f"📊 *INSIGHTS EXAGERADO - Loja {nome_loja}*\n🕒 {agora.strftime('%H:%M')}\n"
                mensagem_final = cabecalho + "\n\n---\n\n".join(relatorio_texto)
                asyncio.run(enviar_mensagem_whatsapp(numero, mensagem_final))

            # --- 2. RELATÓRIO VISUAL (Apenas se enviar_print for True) ---
            if enviar_print:
                logger.info(f"📸 Gerando print para Loja {loja_id}...")
                try:
                    caminho_img = gerar_relatorio_loja_automatizado(df_loja, nome_loja, loja_id, meta_map)
                    with open(caminho_img, "rb") as f:
                        img_data = f.read()
                        asyncio.run(enviar_imagem_whatsapp(
                            numero, 
                            f"🖼️ *RELATÓRIO HORA EM HORA* - {agora.hour}h", 
                            img_data, 
                            caminho_img
                        ))
                    if os.path.exists(caminho_img):
                        os.remove(caminho_img)
                except Exception as e:
                    logger.error(f"❌ Erro no print: {e}")

if __name__ == "__main__":
    logger.info("🚀 Sistema Exagerado Insights Iniciado!")
    
    while True:
        agora = datetime.now()
        hora = agora.hour
        minuto = agora.minute

        # Regra: Evento das 10h às 22h
        if 10 <= hora <= 22:
            # Disparo de hora em hora (ex: 11:00, 12:00...) -> TEXTO + PRINT
            if minuto == 0 and hora >= 11:
                rodar_pipeline_completo(enviar_print=True)
                logger.info("✅ Rodada de hora cheia concluída. Dormindo...")
                time.sleep(60) # Evita disparar duas vezes no mesmo minuto

            # Disparo de 30 em 30 min (ex: 10:30, 11:30...) -> APENAS TEXTO
            elif minuto == 30:
                rodar_pipeline_completo(enviar_print=False)
                logger.info("✅ Rodada de meia hora concluída. Dormindo...")
                time.sleep(60)

            # Pequena espera para não fritar o processador checando o relógio
            time.sleep(30)
            
        else:
            # Fora do horário, espera 10 min e checa de novo
            logger.info(f"🌙 {agora.strftime('%H:%M')} - Fora do horário do evento. Aguardando...")
            time.sleep(600)