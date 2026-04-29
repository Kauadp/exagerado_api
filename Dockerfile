FROM python:3.10-slim

WORKDIR /app

# Instala dependências do sistema para Postgres e Playwright
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    asound2 \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala bibliotecas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala o navegador Chromium para o Playwright
RUN playwright install chromium --with-deps

# Copia o resto do código
COPY . .

# O CMD padrão será a API, mas vamos rodar o main_stats como outro serviço
CMD ["python", "app/receive_print.py"]