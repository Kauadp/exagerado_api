import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from .config import settings
from .database import engine, Base
from .services import processar_venda_completa
import logging

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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)