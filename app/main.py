import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File, Form
from config import settings
from database import engine, Base
from services import processar_venda_completa
import logging
from datetime import datetime

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
        file_size_kb = len(content) / 1024
        
        logger.info(f"\n📸 [SINAL RECEBIDO] - {agora}")
        logger.info(f"   |-- Loja ID: {loja_id}")
        logger.info(f"   |-- Arquivo: {file.filename}")
        logger.info(f"   |-- Tamanho: {file_size_kb:.2f} KB")
        logger.info(f"   |-- Status: Aguardando integração com API de WhatsApp...\n")

        return {
            "status": "received", 
            "loja_id": loja_id, 
            "timestamp": agora,
            "message": "Sinal de print capturado com sucesso no backend!"
        }

    except Exception as e:
        logger.error(f"💥 Erro ao processar sinal de print: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao receber o print")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)