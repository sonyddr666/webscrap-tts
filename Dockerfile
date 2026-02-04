# Dockerfile para Inworld AI TTS Scraper & Telegram Bot
FROM python:3.11-slim

# Evita prompts interativos
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Diretório de trabalho
WORKDIR /app

# Copia dependências primeiro (para cache de build)
COPY requirements.txt .

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código fonte
COPY . .

# Cria diretório de output
RUN mkdir -p /app/output

# Comando padrão (telegram bot)
CMD ["python", "telegram_bot.py"]
