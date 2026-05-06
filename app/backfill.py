import asyncio
import httpx
import os
import json
from datetime import datetime
from services import processar_venda_completa, load_tokens, get_new_token
from database import SessionLocal
from models import VendaItem

BASE_URL = "https://www.bling.com.br/Api/v3/nfce"

# =========================
# VERIFICA SE JÁ FOI PROCESSADO
# =========================
def ja_processado(id_nota):
    db = SessionLocal()
    try:
        existe = db.query(VendaItem).filter(VendaItem.venda_id == id_nota).first()
        return existe is not None
    finally:
        db.close()

# =========================
# BUSCAR NOTAS
# =========================
async def buscar_notas(data_inicio, data_fim):
    tokens = load_tokens()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    pagina = 1
    notas_ids = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            params = {
                "dataInicial": data_inicio,
                "dataFinal": data_fim,
                "pagina": pagina
            }

            response = await client.get(BASE_URL, headers=headers, params=params)

            if response.status_code == 401:
                token = await get_new_token()
                headers["Authorization"] = f"Bearer {token}"
                continue

            if response.status_code != 200:
                print("Erro ao buscar notas:", response.text)
                break

            data = response.json().get("data", [])

            if not data:
                break

            for nota in data:
                notas_ids.append(nota["id"])

            print(f"Página {pagina} carregada ({len(data)} notas)")
            pagina += 1

    return notas_ids

# =========================
# RETRY INTELIGENTE
# =========================
async def processar_com_retry(id_nota, tentativas=3):
    for tentativa in range(tentativas):
        try:
            if ja_processado(id_nota):
                print(f"SKIP {id_nota}")
                return True

            await processar_venda_completa(id_nota)
            print(f"OK {id_nota}")
            return True

        except Exception as e:
            print(f"Erro {id_nota} (tentativa {tentativa+1}): {e}")
            await asyncio.sleep(2 ** tentativa)

    print(f"FALHOU {id_nota}")
    return False

# =========================
# PROCESSAMENTO EM LOTE
# =========================
async def processar_em_lote(notas_ids):
    semaphore = asyncio.Semaphore(5)

    async def worker(id_nota):
        async with semaphore:
            await processar_com_retry(id_nota)

    tasks = [worker(nota_id) for nota_id in notas_ids]
    await asyncio.gather(*tasks)

# =========================
# EXECUÇÃO PRINCIPAL
# =========================
async def rodar_backfill(data_inicio, data_fim):
    print("🔎 Buscando notas...")
    notas = await buscar_notas(data_inicio, data_fim)

    print(f"📦 Total de notas encontradas: {len(notas)}")

    print("⚙️ Reprocessando...")
    await processar_em_lote(notas)

    print("✅ Backfill finalizado!")

if __name__ == "__main__":
    asyncio.run(rodar_backfill("2026-05-05", "2026-05-05"))