import time
import pandas as pd
import logging
from datetime import datetime
import asyncio
from app.database import engine
from app.statistics import AlertaPerformance, AlertaRanking, AlertaLogistica, AlertaBayes
from services import enviar_mensagem_whatsapp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOJAS_ATIVAS = [205906072, 205906073] # MUDAR AQUI

# Mapeamento de IDs da Loja no Bling para Números de WhatsApp
MAP_LOJAS_WPP = {
    205906072: "5527999609988",  # Ex: Gerente Loja 1
}

def rodar_pipeline_texto():
    logger.info(f"🕒 Iniciando rodada de insights: {datetime.now().strftime('%H:%M')}")
    
    try:
        query = "SELECT * FROM vendas_itens WHERE timestamp > now() - interval '48 hours'"
        df_geral = pd.read_sql(query, engine)
        df_geral['timestamp'] = pd.to_datetime(df_geral['timestamp'])
    except Exception as e:
        logger.error(f"❌ Falha ao acessar banco de dados: {e}")
        return

    if df_geral.empty:
        logger.warning("⚠️ Banco vazio. Sem vendas para analisar.")
        return

    for loja_id in LOJAS_ATIVAS:
        df_loja = df_geral[df_geral['id_loja'] == loja_id]
        numero_destino = MAP_LOJAS_WPP.get(loja_id)
        
        if df_loja.empty:
            continue

        # Lista de Processadores de Inteligência
        processadores = [
            AlertaPerformance(df_loja, loja_id),
            AlertaRanking(df_loja, loja_id),
            AlertaLogistica(df_loja, loja_id),
            AlertaBayes(df_loja, loja_id)
        ]

        relatorio_loja = []
        
        for p in processadores:
            try:
                p.analisar()
                texto = p.gerar_texto()
                if texto:
                    relatorio_loja.append(texto)
            except Exception as e:
                logger.error(f"❌ Erro no {p.__class__.__name__} da loja {loja_id}: {e}")

        if relatorio_loja:
            cabecalho = f"📊 *INSIGHTS EXAGERADO* (Loja {loja_id})\n{datetime.now().strftime('%d/%m - %H:%M')}\n"
            mensagem_final = cabecalho + "\n\n---\n\n".join(relatorio_loja)
            logger.info(f"📱 Enviando para {numero_destino} (Loja {loja_id})")
            asyncio.run(enviar_mensagem_whatsapp(numero_destino, mensagem_final))

if __name__ == "__main__":
    while True:
        agora = datetime.now()
        
        # Só roda entre 10h e 22h
        if 10 <= agora.hour <= 22:
            rodar_pipeline_texto()
            
            # Espera 30 minutos
            logger.info("💤 Sleeping for 30 min...")
            time.sleep(1800)
        else:
            # Fora do horário, checa a cada 15 min se já deu 10h
            logger.info("🌙 Fora do horário de operação. Aguardando...")
            time.sleep(900)