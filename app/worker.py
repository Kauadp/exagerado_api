import asyncio
from database import SessionLocal
from models import WebhookEvent
from services import processar_venda_completa
import logging

logger = logging.getLogger(__name__)

semaphore = asyncio.Semaphore(5)


async def processar_evento(evento_id):
    db = SessionLocal()
    try:
        evento = db.get(WebhookEvent, evento_id)

        if not evento:
            return

        try:
            async with semaphore:
                await processar_venda_completa(evento.id_nota)

            evento.status = "done"
            db.commit()

        except Exception as e:
            erro = str(e)

            if "NOTA_NAO_ENCONTRADA" in erro:
                evento.tentativas += 1

                if evento.tentativas >= 10:
                    evento.status = "ignored"
                else:
                    evento.status = "pending"

                logger.warning(f"⚠️ Nota {evento.id_nota} não encontrada (tentativa {evento.tentativas})")
                delay = min(5 * (2 ** evento.tentativas - 1), 60)

                db.commit()
                await asyncio.sleep(delay)
                return

            elif "RATE_LIMIT" in erro:
                evento.tentativas += 1
                evento.status = "pending"

                logger.warning(f"⏳ Rate limit (tentativa {evento.tentativas})")

                db.commit()
                await asyncio.sleep(2 ** evento.tentativas)
                return

            else:
                evento.tentativas += 1
                evento.status = "error"

                logger.error(f"❌ Erro no evento {evento.id_nota}: {e}")

                db.commit()
                return
    finally:
        db.close()


async def worker_loop():
    while True:
        db = SessionLocal()
        try:
            eventos = (
                db.query(WebhookEvent)
                .filter(
                    (WebhookEvent.status == "pending") |
                    ((WebhookEvent.status == "error") & (WebhookEvent.tentativas < 10))
                )
                .with_for_update(skip_locked=True)
                .limit(10)
                .all()
            )

            ids = []

            if eventos:
                for evento in eventos:
                    evento.status = "processing"

                db.commit()
                ids = [e.id for e in eventos]

                logger.info(f"Processando lote de {len(ids)} eventos")

        finally:
            db.close()

        if ids:
            tasks = [processar_evento(e_id) for e_id in ids]
            await asyncio.gather(*tasks)

        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(worker_loop())