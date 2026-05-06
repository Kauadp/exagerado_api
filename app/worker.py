import asyncio
from database import SessionLocal
from models import WebhookEvent
from services import processar_venda_completa
import logging

logger = logging.getLogger(__name__)

semaphore = asyncio.Semaphore(2)


async def processar_evento(evento_id):
    db = SessionLocal()
    try:
        evento = db.get(WebhookEvent, evento_id)
        if not evento:
            return

        try:
            async with semaphore:
                await processar_venda_completa(evento.id_nota)
                await asyncio.sleep(0.4)  # respeita 3 req/s do Bling

            evento.status = "done"
            db.commit()
            logger.info(f"✅ Nota {evento.id_nota} processada")

        except Exception as e:
            erro = str(e)
            evento.tentativas += 1

            if "NOTA_NAO_ENCONTRADA" in erro:
                evento.status = "ignored" if evento.tentativas >= 10 else "pending"
                logger.warning(f"⚠️ Nota {evento.id_nota} não encontrada (tentativa {evento.tentativas})")

            elif "429" in erro or "TOO_MANY" in erro or "RATE" in erro:
                evento.status = "pending"
                logger.warning(f"⏳ Rate limit na nota {evento.id_nota}, voltando pra fila")
                db.commit()
                await asyncio.sleep(5)  # espera antes de liberar o semaphore
                return

            else:
                evento.status = "error"
                logger.error(f"❌ Erro nota {evento.id_nota} (tentativa {evento.tentativas}): {e}")

            db.commit()

    finally:
        db.close()


async def worker_loop():
    logger.info("🚀 Worker iniciado")
    while True:
        db = SessionLocal()
        ids = []
        try:
            eventos = (
                db.query(WebhookEvent)
                .filter(
                    (WebhookEvent.status == "pending") |
                    ((WebhookEvent.status == "error") & (WebhookEvent.tentativas < 10))
                )
                .with_for_update(skip_locked=True)
                .order_by(WebhookEvent.criado_em.asc())  # processa mais antigos primeiro
                .limit(20)
                .all()
            )

            if eventos:
                for evento in eventos:
                    evento.status = "processing"  # ← fix do bug principal
                db.commit()
                ids = [e.id for e in eventos]
                logger.info(f"📦 Lote de {len(ids)} eventos")

        finally:
            db.close()

        if ids:
            tasks = [processar_evento(e_id) for e_id in ids]
            await asyncio.gather(*tasks)
        else:
            await asyncio.sleep(3)  # fila vazia, dorme mais

        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(worker_loop())