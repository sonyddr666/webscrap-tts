# Telegram TTS Bot v3 - Com Comandos e Queue
# =============================================
# Comandos: /voice, /voices, /idioma
# Sistema de queue para processamento de áudio

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
from typing import Dict, List, Optional

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Carrega variáveis de ambiente
load_dotenv()

# ============================================================
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
INWORLD_TOKEN = os.getenv("INWORLD_TOKEN")
WORKSPACE_ID = os.getenv("WORKSPACE_ID", "default--pb4bm1oowkem_r9ri2wiw")

BASE_URL = "https://api.inworld.ai"
DELAY_DELETE_SEGUNDOS = 50

# Diretórios
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# ESTADO GLOBAL
# ============================================================

# Voz atual por usuário (user_id -> voice_id)
user_voices: Dict[int, str] = {}

# Voz padrão
DEFAULT_VOICE = os.getenv("TTS_VOICE_ID", "default--pb4bm1oowkem_r9ri2wiw__sony")

# Idiomas suportados
IDIOMAS = {
    'pt': '🇧🇷 Português',
    'en': '🇺🇸 English',
    'es': '🇪🇸 Español',
    'fr': '🇫🇷 Français',
    'de': '🇩🇪 Deutsch',
    'it': '🇮🇹 Italiano',
    'ja': '🇯🇵 日本語',
    'ko': '🇰🇷 한국어',
    'zh': '🇨🇳 中文',
}

# Cache de vozes
voices_cache: List[dict] = []
voices_cache_time: float = 0

# ============================================================
# QUEUE DE ÁUDIO
# ============================================================

audio_queue: asyncio.Queue = None
queue_worker_task = None

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
]

# ============================================================
# FUNÇÕES API INWORLD
# ============================================================

def get_headers():
    return {
        "Authorization": f"Bearer {INWORLD_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://platform.inworld.ai",
        "Referer": "https://platform.inworld.ai/",
    }


def fetch_voices(filtro_idioma: str = None) -> List[dict]:
    """Busca vozes da API Inworld"""
    global voices_cache, voices_cache_time
    
    # Cache de 5 minutos
    if voices_cache and (time.time() - voices_cache_time) < 300:
        voices = voices_cache
    else:
        url = f"{BASE_URL}/voices/v1/workspaces/{WORKSPACE_ID}/voices"
        try:
            response = requests.get(url, headers=get_headers(), timeout=30)
            response.raise_for_status()
            voices = response.json().get('voices', [])
            voices_cache = voices
            voices_cache_time = time.time()
            logger.info(f"📥 Carregadas {len(voices)} vozes da API")
        except Exception as e:
            logger.error(f"Erro ao buscar vozes: {e}")
            return []
    
    # Filtra por idioma se especificado
    if filtro_idioma:
        voices = [v for v in voices if filtro_idioma in v.get('languages', [])]
    
    return voices


def generate_audio_direct(text: str, voice_id: str, filename: Path) -> Optional[str]:
    """Gera áudio usando a API TTS"""
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
    
    logger.info(f"🎙️ Gerando: '{text[:40]}...' com voz {voice_id[-20:]}")
    time.sleep(random.uniform(0.3, 0.8))
    
    response = requests.post(url, headers=get_headers(), json=payload, timeout=60)
    
    if response.status_code != 200:
        logger.error(f"❌ API erro: {response.status_code}")
        return None
    
    data = response.json()
    if 'audioContent' not in data:
        logger.error(f"❌ Sem audioContent")
        return None
    
    audio_bytes = base64.b64decode(data['audioContent'])
    if len(audio_bytes) < 100:
        logger.error(f"❌ Áudio vazio")
        return None
    
    with open(filename, "wb") as f:
        f.write(audio_bytes)
    
    logger.info(f"✅ Salvo: {filename.name} ({len(audio_bytes)/1024:.1f}KB)")
    return str(filename)


# ============================================================
# QUEUE WORKER
# ============================================================

async def queue_worker():
    """Processa a fila de áudio"""
    global audio_queue
    
    while True:
        try:
            item = await audio_queue.get()
            update = item['update']
            texto = item['texto']
            voice_id = item['voice_id']
            user = update.effective_user
            
            # Gera o áudio
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = OUTPUT_DIR / f"tg_{user.id}_{timestamp}.mp3"
            
            resultado = generate_audio_direct(texto, voice_id, filename)
            
            if resultado and os.path.exists(resultado):
                with open(resultado, 'rb') as audio_file:
                    await update.message.reply_voice(
                        voice=audio_file,
                        caption="🎙️ TTS gerado!"
                    )
                logger.info(f"✅ Enviado para {user.first_name}")
                
                # Deleta após 50s
                asyncio.create_task(deletar_arquivo_depois(resultado))
            else:
                await update.message.reply_text("❌ Falha ao gerar áudio.")
            
            audio_queue.task_done()
            
        except Exception as e:
            logger.error(f"Erro no worker: {e}")


async def deletar_arquivo_depois(caminho: str, delay: int = DELAY_DELETE_SEGUNDOS):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
            logger.info(f"🗑️ Deletado: {caminho}")
    except Exception as e:
        logger.error(f"Erro ao deletar: {e}")


# ============================================================
# HANDLERS - COMANDOS
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    voice = user_voices.get(user_id, DEFAULT_VOICE)
    voice_name = voice.split('__')[-1] if '__' in voice else voice
    
    await update.message.reply_text(
        "🎙️ **Bot TTS Inworld AI v3**\n\n"
        "Envie texto para gerar áudio!\n\n"
        "**Comandos:**\n"
        "• /voices - Lista vozes\n"
        "• /voice - Trocar voz\n"
        "• /idioma - Filtrar por idioma\n\n"
        f"🎤 Voz atual: `{voice_name}`",
        parse_mode="Markdown"
    )


async def voices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista vozes disponíveis"""
    await update.message.reply_text("🔍 Buscando vozes...")
    
    voices = fetch_voices()
    
    if not voices:
        await update.message.reply_text("❌ Não foi possível carregar vozes.")
        return
    
    # Monta lista (máximo 15)
    texto = "🎤 **Vozes Disponíveis:**\n\n"
    for i, voice in enumerate(voices[:15], 1):
        name = voice.get('displayName', 'Sem nome')
        langs = ', '.join(voice.get('languages', [])[:2])
        texto += f"`{i}.` **{name}** ({langs})\n"
    
    if len(voices) > 15:
        texto += f"\n_...e mais {len(voices) - 15} vozes_\n"
    
    texto += "\n💡 Use /idioma para filtrar por idioma"
    
    await update.message.reply_text(texto, parse_mode="Markdown")


async def idioma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de seleção de idioma"""
    keyboard = []
    row = []
    
    for code, name in IDIOMAS.items():
        row.append(InlineKeyboardButton(name, callback_data=f"idioma:{code}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🌍 **Escolha o idioma das vozes:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu para trocar voz"""
    user_id = update.effective_user.id
    current_voice = user_voices.get(user_id, DEFAULT_VOICE)
    current_name = current_voice.split('__')[-1] if '__' in current_voice else current_voice
    
    # Busca vozes para português por padrão
    voices = fetch_voices('pt')[:9]  # Máximo 9 para caber nos botões
    
    if not voices:
        await update.message.reply_text("❌ Erro ao carregar vozes.")
        return
    
    keyboard = []
    row = []
    
    for voice in voices:
        name = voice.get('displayName', '?')[:12]
        voice_id = voice.get('voiceId') or voice.get('name', '')
        
        # Marca a voz atual
        prefix = "✓ " if voice_id == current_voice else ""
        
        row.append(InlineKeyboardButton(
            f"{prefix}{name}",
            callback_data=f"voice:{voice_id}"
        ))
        
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎤 **Voz atual:** `{current_name}`\n\n"
        "Escolha uma nova voz:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# ============================================================
# HANDLER - CALLBACKS (BOTÕES)
# ============================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques nos botões inline"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("idioma:"):
        # Selecionou idioma -> mostra vozes desse idioma
        idioma = data.split(":")[1]
        voices = fetch_voices(idioma)
        
        if not voices:
            await query.edit_message_text(f"❌ Nenhuma voz encontrada para {IDIOMAS.get(idioma, idioma)}")
            return
        
        keyboard = []
        row = []
        
        for voice in voices[:12]:
            name = voice.get('displayName', '?')[:12]
            voice_id = voice.get('voiceId') or voice.get('name', '')
            
            row.append(InlineKeyboardButton(
                name,
                callback_data=f"voice:{voice_id}"
            ))
            
            if len(row) == 3:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🎤 **Vozes em {IDIOMAS.get(idioma, idioma)}:**\n\nEscolha uma:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif data.startswith("voice:"):
        # Selecionou voz
        voice_id = data.split(":", 1)[1]
        user_voices[user_id] = voice_id
        
        voice_name = voice_id.split('__')[-1] if '__' in voice_id else voice_id
        
        await query.edit_message_text(
            f"✅ **Voz alterada!**\n\n🎤 Nova voz: `{voice_name}`\n\nAgora envie um texto para testar!",
            parse_mode="Markdown"
        )
        logger.info(f"🔄 {query.from_user.first_name} trocou voz para: {voice_name}")


# ============================================================
# HANDLER - MENSAGENS DE TEXTO
# ============================================================

async def processar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona texto à fila de processamento"""
    global audio_queue
    
    texto = update.message.text.strip()
    if not texto:
        return
    
    if len(texto) > 2000:
        await update.message.reply_text("⚠️ Texto muito longo. Máximo: 2000 caracteres.")
        texto = texto[:2000]
    
    user = update.effective_user
    voice_id = user_voices.get(user.id, DEFAULT_VOICE)
    
    logger.info(f"📩 {user.first_name}: {texto[:40]}...")
    
    # Adiciona à fila
    queue_size = audio_queue.qsize()
    
    await audio_queue.put({
        'update': update,
        'texto': texto,
        'voice_id': voice_id
    })
    
    if queue_size > 0:
        await update.message.reply_text(f"⏳ Fila: posição {queue_size + 1}")
    else:
        await update.message.chat.send_action("record_voice")


# ============================================================
# MAIN
# ============================================================

async def post_init(application):
    """Inicializa a queue após o bot iniciar"""
    global audio_queue, queue_worker_task
    audio_queue = asyncio.Queue()
    queue_worker_task = asyncio.create_task(queue_worker())
    logger.info("🚀 Queue worker iniciado!")


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🤖 TELEGRAM TTS BOT v3                                     ║
║                                                              ║
║   Comandos: /voice /voices /idioma                           ║
║   Queue de áudio ativada                                     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN não encontrado!")
        return
    
    if not INWORLD_TOKEN:
        logger.error("❌ INWORLD_TOKEN não encontrado!")
        return
    
    logger.info(f"🎤 Voz padrão: {DEFAULT_VOICE}")
    
    # Cria aplicação
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("voices", voices_command))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("idioma", idioma_command))
    
    # Callbacks (botões)
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Mensagens de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_texto))
    
    logger.info("🚀 Bot iniciado!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
