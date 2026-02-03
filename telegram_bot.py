# Telegram TTS Bot - Usando Inworld AI Scraper
# =============================================
# Bot que recebe texto, gera áudio via TTS e envia ao usuário.
# O arquivo de áudio é deletado 50 segundos após o envio.

import os
import asyncio
import logging
import requests
import json
import base64
import time
import random
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Carrega variáveis de ambiente
load_dotenv()

# ============================================================
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
INWORLD_TOKEN = os.getenv("INWORLD_TOKEN")
WORKSPACE_ID = os.getenv("WORKSPACE_ID", "default--pb4bm1oowkem_r9ri2wiw")
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID", "pt-BR-Francisca")  # Voice ID fixo

BASE_URL = "https://api.inworld.ai"
DELAY_DELETE_SEGUNDOS = 50  # Tempo antes de deletar o arquivo

# Diretórios
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# User-Agents para rotação
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
]

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def get_headers():
    """Gera headers realistas"""
    return {
        "Authorization": f"Bearer {INWORLD_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://platform.inworld.ai",
        "Referer": "https://platform.inworld.ai/",
    }


def generate_audio_direct(text: str, voice_id: str, filename: Path) -> str:
    """Gera áudio usando a API TTS diretamente"""
    url = f"{BASE_URL}/tts/v1/voice"
    
    payload = {
        "text": text,
        "voice_id": voice_id,
        "model_id": "inworld-tts-1.5-max",
        "audio_config": {
            "audio_encoding": "MP3",
            "speaking_rate": 1,
            "sample_rate_hertz": 48000
        },
        "temperature": 1.0
    }
    
    logger.info(f"🎙️ Gerando áudio: '{text[:50]}...'")
    
    # Delay humano
    time.sleep(random.uniform(0.5, 1.5))
    
    response = requests.post(url, headers=get_headers(), json=payload, timeout=60)
    response.raise_for_status()
    
    content_type = response.headers.get('Content-Type', '')
    
    # Processa resposta (JSON com Base64 ou bytes brutos)
    if 'application/json' in content_type:
        data = response.json()
        if 'audioContent' in data:
            audio_bytes = base64.b64decode(data['audioContent'])
            with open(filename, "wb") as f:
                f.write(audio_bytes)
            logger.info(f"✅ Áudio salvo: {filename} ({len(audio_bytes)/1024:.1f} KB)")
            return str(filename)
        else:
            logger.error(f"JSON sem 'audioContent': {list(data.keys())}")
            return None
    else:
        # Bytes brutos
        with open(filename, "wb") as f:
            f.write(response.content)
        logger.info(f"✅ Áudio salvo: {filename} ({len(response.content)/1024:.1f} KB)")
        return str(filename)


async def deletar_arquivo_depois(caminho: str, delay: int = DELAY_DELETE_SEGUNDOS):
    """Aguarda 'delay' segundos e então deleta o arquivo."""
    await asyncio.sleep(delay)
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
            logger.info(f"🗑️ Arquivo deletado: {caminho}")
    except Exception as e:
        logger.error(f"Erro ao deletar arquivo {caminho}: {e}")


# ============================================================
# HANDLERS DO BOT
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /start"""
    await update.message.reply_text(
        "🎙️ **Bot TTS Inworld AI**\n\n"
        "Envie qualquer texto e eu vou gerar um áudio para você!\n\n"
        f"🎤 Voz: `{TTS_VOICE_ID}`\n"
        "⏱️ O áudio será removido do servidor após 50 segundos.",
        parse_mode="Markdown"
    )


async def processar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para mensagens de texto - gera TTS"""
    texto = update.message.text.strip()
    
    if not texto:
        return
    
    # Limita texto a 2000 caracteres
    if len(texto) > 2000:
        await update.message.reply_text(
            f"⚠️ Texto muito longo ({len(texto)} chars). Máximo: 2000. Truncando..."
        )
        texto = texto[:2000]
    
    user = update.effective_user
    logger.info(f"📩 Mensagem de {user.first_name} (ID: {user.id}): {texto[:50]}...")
    
    # Envia "gravando áudio..."
    await update.message.chat.send_action("record_voice")
    
    try:
        # Gera nome único para o arquivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = OUTPUT_DIR / f"tg_{user.id}_{timestamp}.mp3"
        
        resultado = generate_audio_direct(texto, TTS_VOICE_ID, filename)
        
        if resultado and os.path.exists(resultado):
            # Envia o áudio
            with open(resultado, 'rb') as audio_file:
                await update.message.reply_voice(
                    voice=audio_file,
                    caption=f"🎙️ TTS gerado com sucesso!"
                )
            
            logger.info(f"✅ Áudio enviado para {user.first_name}")
            
            # Agenda deleção do arquivo após 50 segundos
            asyncio.create_task(deletar_arquivo_depois(resultado))
        else:
            await update.message.reply_text(
                "❌ Falha ao gerar áudio. Tente novamente."
            )
            logger.error(f"Falha ao gerar áudio para: {texto[:50]}...")
    
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        logger.error(f"Erro HTTP {status}: {e}")
        
        if status == 401:
            await update.message.reply_text("❌ Token expirado. Atualize o INWORLD_TOKEN no .env")
        elif status == 429:
            await update.message.reply_text("⏳ Rate limit atingido. Aguarde um momento.")
        else:
            await update.message.reply_text(f"❌ Erro na API: {status}")
    
    except Exception as e:
        logger.error(f"Erro ao processar texto: {e}")
        await update.message.reply_text(
            "❌ Ocorreu um erro ao processar sua mensagem."
        )


# ============================================================
# MAIN
# ============================================================

def main():
    """Inicializa e roda o bot"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🤖 TELEGRAM TTS BOT v2                                     ║
║                                                              ║
║   Powered by Inworld AI TTS                                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Verifica token do Telegram
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN não encontrado no .env!")
        return
    
    # Verifica token da Inworld
    if not INWORLD_TOKEN:
        logger.error("❌ INWORLD_TOKEN não encontrado no .env!")
        return
    
    logger.info(f"🎤 Usando voz: {TTS_VOICE_ID}")
    
    # Cria a aplicação
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Registra handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_texto))
    
    # Inicia o bot
    logger.info("🚀 Bot iniciado! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
