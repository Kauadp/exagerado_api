import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File, Form
from config import settings
from database import engine, Base
from services import processar_venda_completa, enviar_imagem_whatsapp
import logging
from datetime import datetime
from main_stats import rodar_pipeline_completo
from dotenv import load_dotenv
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import asyncio

load_dotenv()

WEBHOOK_TOKEN=os.getenv("WEBHOOK_TOKEN")

# Configuração centralizada
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Mapeamento de IDs da Loja no Bling para Números de WhatsApp
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

# Cria as tabelas na inicialização
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Exagerado Insights API")

@app.post("/webhook")
async def bling_webhook(request: Request, token: str, background_tasks: BackgroundTasks):
    if token != settings.WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Não Autorizado")
    
    payload = await request.json()
    id_nota = payload.get("data", {}).get("id")

    if id_nota:
        background_tasks.add_task(processar_venda_completa, id_nota)
        return {"status": "success", "message": "Processando nota..."}
    
    return {"status": "error", "message": "ID não encontrado"}

@app.post("/alerts/send-print")
async def receive_print_signal(
    background_tasks: BackgroundTasks,
    token: str,
    loja_id: int = Form(...), 
    file: UploadFile = File(...)
):
    """
    Endpoint temporário para validar o recebimento dos prints do Dashboard.
    Sinaliza no console que o arquivo chegou com sucesso.
    """
    if token != settings.WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Não Autorizado")
    
    agora = datetime.now().strftime('%H:%M:%S')
    
    if not file.content_type.startswith("image/"):
        logger.warning(f"⚠️ [{agora}] Tentativa de envio de arquivo inválido pela Loja {loja_id}")
        raise HTTPException(status_code=400, detail="O arquivo enviado não é uma imagem.")

    try:
        content = await file.read()
        numero_destino = MAP_LOJAS_WPP.get(loja_id, [])
        logger.info(f"\n📸 [SINAL RECEBIDO] - {agora}")
        legenda = f"📸 *Dashboard Capturado* - Loja {loja_id}\nEm: {datetime.now().strftime('%H:%M:%S')}"
        for numero in numero_destino:
            background_tasks.add_task(
                enviar_imagem_whatsapp, 
                numero, 
                legenda, 
                content, 
                file.filename
            )

            return {"status": "sent_to_queue", "target": numero}

    except Exception as e:
        logger.error(f"💥 Erro ao processar sinal de print: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao receber o print")


executor = ThreadPoolExecutor(max_workers=3)

def executar_pipeline_sync(loja_id, enviar_print):
    """
    Esta função roda a lógica original (síncrona) 
    em uma thread separada para não travar o FastAPI.
    """
    return rodar_pipeline_completo(enviar_print=enviar_print)

@app.post("/trigger-pipeline")
async def trigger_full_pipeline(loja_id: int, token: str):
    if token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")
    try:
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(executor, executar_pipeline_sync, loja_id, True)
        
        return {"status": "success", "message": f"Pipeline da loja {loja_id} executado com sucesso!"}
    
    except Exception as e:
        logger.error(f"Erro ao rodar pipeline manual: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)