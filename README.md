# Exagerado Insights API

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/Banco-PostgreSQL-336791?logo=postgresql)
![Docker](https://img.shields.io/badge/Container-Docker-2496ED?logo=docker)
![Status](https://img.shields.io/badge/Status-Development-yellow)

---

## Visão Geral

API em Python que integra dados de vendas do **Bling ERP** com **PostgreSQL**, processando webhooks de transações comerciais e disparando alertas em tempo real via **WhatsApp**.

O projeto automatiza a coleta e monitoramento de dados de vendas, fornecendo visibilidade instantânea sobre operações comerciais sem intervenção manual.

---

## Estrutura

```
├── app/
│   ├── config.py             # Variáveis de ambiente e secrets
│   ├── database.py           # Engine SQLAlchemy + pool de conexões
│   ├── models.py             # Modelos ORM (VendaItem, etc)
│   ├── main.py               # FastAPI app + endpoint webhook
│   ├── services.py           # Lógica de negócio (Bling + WhatsApp)
│   ├── database.py           # Configuração do banco
│   ├── statistics.py         # Cálculos e agregações de dados
│   ├── main_stats.py         # Endpoints de estatísticas
│   └── test_zap.py           # Testes de integração WhatsApp
├── Dockerfile                # Container da aplicação
├── docker-compose.yml        # Orquestração (API + PostgreSQL)
├── requirements.txt          # Dependências Python
├── .env                      # Configurações sensíveis (não commitar)
├── app.log                   # Logs da aplicação
└── README.md
```

---

## Arquitetura

### Fluxo de Dados

```
Bling ERP 
    ↓
[Webhook POST /webhook]
    ↓
[FastAPI - Validação de token]
    ↓
[processar_venda_completa()]
    ├─→ Consulta API Bling
    ├─→ Extrai dados de itens
    ├─→ Salva em PostgreSQL
    └─→ Dispara alertas WhatsApp
```

### Banco de Dados

**Tabelas PostgreSQL:**

- **`vendas_itens`** — registro de cada item vendido
  - `id`: chave primária
  - `venda_id`: ID da nota no Bling
  - `id_loja`: loja que gerou a venda
  - `produto_id`: código do produto
  - `sku`: código SKU
  - `quantidade`: unidades vendidas
  - `valor_unitario`: preço por unidade
  - `valor_total`: total do item
  - `estoque_pos_venda`: estoque após a transação
  - `timestamp`: data/hora do registro

---

## Endpoints

### `POST /webhook`

Recebe webhook do Bling ao confirmar uma venda.

**Parâmetros:**
- `token` (query): token de autenticação
- `payload` (body): dados da nota fiscal

**Resposta:**
```json
{
  "status": "success",
  "message": "Processando nota..."
}
```

**Fluxo:**
1. Valida token
2. Extrai ID da nota
3. Inicia processamento assíncrono
4. Salva itens em `vendas_itens`
5. Envia alertas via WhatsApp para gerentes

---

### `POST /alerts/send-print`

Recebe sinal de impressão e envia print via WhatsApp.

**Parâmetros:**
- `token` (query): token de autenticação
- `loja_id` (form): ID da loja
- `file` (form): arquivo de imagem

**Resposta:**
```json
{
  "status": "success",
  "file": "nome_arquivo.jpg"
}
```

---

## Configuração

### Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```bash
# Bling API
BLING_ACCESS_TOKEN=seu_token_bling
BLING_REFRESH_TOKEN=seu_refresh_token
BLING_CLIENT_ID=seu_client_id
BLING_CLIENT_SECRET=seu_client_secret

# Segurança
WEBHOOK_TOKEN=seu_token_secreto_aqui

# Banco de Dados
DATABASE_URL=postgresql://user:password@db:5432/exagerado_db

# WhatsApp
WHATSAPP_API_TOKEN=seu_token_whatsapp
WHATSAPP_PHONE_ID=seu_phone_id

# Aplicação
ENVIRONMENT=development
```

### Instalação de Dependências

```bash
pip install -r requirements.txt
```

### Com Docker Compose

```bash
docker-compose up --build
```

Ou sem rebuild:
```bash
docker-compose up -d
```

---

## Integração com Bling

O Bling é um ERP para e-commerce. A integração acontece via:

1. **Webhook** — Bling notifica a API sempre que uma venda é confirmada
2. **API REST** — consultamos detalhes da nota e itens
3. **OAuth 2.0** — autenticação via tokens

### Configurar Webhook no Bling

1. Acesse: Dashboard Bling → Configurações → Webhooks
2. Adicione a URL: `https://seu-dominio.com/webhook?token=seu_token_secreto`
3. Selecione o evento: `Nota Fiscal - Vendas`
4. Salve

---

## Alertas WhatsApp

Quando uma venda é processada com sucesso:

1. Sistema identifica a loja (`id_loja`)
2. Busca o número de WhatsApp mapeado em `MAP_LOJAS_WPP`
3. Envia mensagem com resumo da venda (quantidade, valor, produtos)
4. Inclui link para dashboard se disponível

### Mapeamento de Lojas

Editar em `app/main.py`:

```python
MAP_LOJAS_WPP = {
    205906072: "5527999609988",  # Gerente Loja ES
    205906073: "5527999609989",  # Gerente Loja RJ
}
```

---

## Tecnologias

- **Python 3.10** — linguagem
- **FastAPI** — framework web
- **PostgreSQL** — banco de dados
- **SQLAlchemy** — ORM
- **psycopg2** — driver PostgreSQL
- **Pydantic** — validação de dados
- **Uvicorn** — servidor ASGI
- **Docker** — containerização
- **Requests** — HTTP client
- **python-dotenv** — gerenciamento de secrets

---

## Desenvolvimento

### Executar Localmente

```bash
# Ativar venv
source venv/bin/activate

# Instalar deps
pip install -r requirements.txt

# Rodar servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API estará disponível em: `http://localhost:8000`

Docs interativa (Swagger): `http://localhost:8000/docs`

### Estrutura de Logs

Logs são salvos em `app.log` e exibidos no console:

```
2026-04-28 14:23:45 - app - INFO - Webhook recebido de ID 123456
2026-04-28 14:23:46 - app - DEBUG - Processando venda 123456
2026-04-28 14:23:47 - app - INFO - Venda salva com sucesso
2026-04-28 14:23:48 - app - INFO - Alerta WhatsApp enviado para 5527999609988
```

---

## Fluxo de Processamento

### 1. Recebimento do Webhook

FastAPI valida o token e extrai o ID da nota:

```python
@app.post("/webhook")
async def bling_webhook(request: Request, token: str, background_tasks: BackgroundTasks):
    if token != settings.WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Não Autorizado")
    
    payload = await request.json()
    id_nota = payload.get("data", {}).get("id")
    
    if id_nota:
        background_tasks.add_task(processar_venda_completa, id_nota)
        return {"status": "success"}
```

### 2. Processamento Assíncrono

A função `processar_venda_completa()`:

- Consulta API do Bling com o ID da nota
- Extrai lista de itens vendidos
- Itera cada item e persiste em `vendas_itens`
- Dispara alerta WhatsApp para o gerente da loja
- Registra erros em logs

### 3. Persistência

Dados são salvos diretamente em PostgreSQL:

```python
session.add(VendaItem(
    venda_id=id_nota,
    id_loja=loja_id,
    produto_id=produto["id"],
    sku=produto["sku"],
    nome_produto=produto["nome"],
    quantidade=produto["quantidade"],
    valor_unitario=produto["valor_unitario"],
    valor_total=produto["valor_total"],
    timestamp=datetime.now()
))
session.commit()
```

### 4. Notificação

Mensagem enviada via WhatsApp inclui:
- ID da venda
- Total de itens
- Valor total
- Horário da transação

---

## Troubleshooting

### Erro: "Não Autorizado" ao receber webhook

Verifique se o token está correto:
```bash
echo $WEBHOOK_TOKEN
```

E se está passando na URL:
```
http://seu-dominio.com/webhook?token=seu_token_secreto
```

### Erro: Connection refused ao banco de dados

Verifique se o container PostgreSQL está rodando:
```bash
docker-compose ps
```

Inicie se necessário:
```bash
docker-compose up -d db
```

### Erro: API Token Bling expirado

Tokens Bling expiram a cada 24h. Implemente refresh:

```python
def renovar_token_bling():
    # Consultar app/services.py para lógica de refresh
    pass
```

---

## Plano de Desenvolvimento

- [ ] Dashboard de vendas em Streamlit
- [ ] Análise de tendências com Prophet
- [ ] Alertas inteligentes (anomalias)
- [ ] Integração com Slack
- [ ] Cache de dados com Redis
- [ ] Testes automatizados com pytest
- [ ] Deploy em produção (AWS/GCP)

---

## Autor

**Kauã Dias**  
Estudante de Estatística | Data Science | Automação com Python

- GitHub: [Kauadp](https://github.com/Kauadp)
- LinkedIn: [kauad](https://www.linkedin.com/in/kauad/)

---
