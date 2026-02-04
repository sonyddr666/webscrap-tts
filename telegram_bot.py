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

# Firebase Token Refresh
FIREBASE_API_KEY = 
FIREBASE_REFRESH_TOKEN = os.getenv("FIREBASE_REFRESH_TOKEN", ")

# Token atual (pode ser renovado)
current_token = INWORLD_TOKEN

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

# Mapeamento de vozes por idioma (baseado na documentação Inworld)
VOICE_LANGUAGES = {
    # English
    'Blake': 'en', 'Clive': 'en', 'Hades': 'en', 'Hana': 'en', 'Luna': 'en',
    'Mark': 'en', 'Olivia': 'en', 'Theodore': 'en', 'Alex': 'en', 'Ashley': 'en',
    'Carter': 'en', 'Craig': 'en', 'Deborah': 'en', 'Dennis': 'en', 'Dominus': 'en',
    'Edward': 'en', 'Pixie': 'en', 'Ronald': 'en', 'Sarah': 'en', 'Timothy': 'en',
    'Wendy': 'en',
    # Portuguese
    'sony': 'pt', 'Heitor': 'pt', 'Maitê': 'pt',
    # Spanish
    'Diego': 'es', 'Lupita': 'es', 'Miguel': 'es', 'Rafael': 'es',
    # French
    'Alain': 'fr', 'Étienne': 'fr', 'Hélène': 'fr', 'Mathieu': 'fr',
    # German
    'Johanna': 'de', 'Josef': 'de',
    # Japanese
    'Asuka': 'ja', 'Satoshi': 'ja',
    # Korean
    'Hyunwoo': 'ko', 'Minji': 'ko', 'Seojun': 'ko', 'Yoona': 'ko',
    # Chinese
    'Jing': 'zh', 'Xiaoyin': 'zh', 'Xinyi': 'zh', 'Yichen': 'zh',
    # Russian
    'Dmitry': 'ru', 'Elena': 'ru', 'Nikolai': 'ru', 'Svetlana': 'ru',
    # Dutch
    'Erik': 'nl', 'Katrien': 'nl', 'Lennart': 'nl', 'Lore': 'nl',
    # Italian
    'Gianni': 'it', 'Orietta': 'it',
    # Arabic
    'Nour': 'ar', 'Omar': 'ar',
    # Hebrew
    'Oren': 'he', 'Yael': 'he',
    # Hindi
    'Manoj': 'hi', 'Riya': 'hi',
    # Polish
    'Szymon': 'pl', 'Wojciech': 'pl',
}

# Idiomas para o menu
IDIOMAS = {
    'all': '🌍 Todas',
    'en': '🇺🇸 English',
    'pt': '🇧🇷 Português',
    'es': '🇪🇸 Español',
    'fr': '🇫🇷 Français',
    'de': '🇩🇪 Deutsch',
    'ja': '🇯🇵 日本語',
    'ko': '🇰🇷 한국어',
    'zh': '🇨🇳 中文',
    'ru': '🇷🇺 Русский',
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
    level=logging.DEBUG,
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

def refresh_firebase_token():
    """Renova o accessToken usando o refreshToken do Firebase"""
    try:
        url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
        payload = {"grant_type": "refresh_token", "refresh_token": FIREBASE_REFRESH_TOKEN}
        response = requests.post(url, data=payload, timeout=30)
        if response.status_code == 200:
            return response.json().get("id_token")
    except Exception as e:
        logger.error(f"Erro ao renovar Firebase token: {e}")
    return None


def refresh_inworld_token():
    """Gera novo token Inworld TTS usando Firebase"""
    global current_token
    
    firebase_token = refresh_firebase_token()
    if not firebase_token:
        logger.error("❌ Falha ao obter Firebase token")
        return None
    
    try:
        # Endpoint correto que gera token com scope we:tts
        url = f"https://platform.inworld.ai/ai/inworld/portal/v1alpha/workspaces/{WORKSPACE_ID}/token:generate"
        headers = {
            "authorization": f"Bearer {firebase_token}",
            "content-type": "text/plain;charset=UTF-8",
            "grpc-metadata-x-authorization-bearer-type": "firebase",
            "origin": "https://platform.inworld.ai",
            "referer": f"https://platform.inworld.ai/v2/workspaces/{WORKSPACE_ID}/tts-playground",
        }
        payload = json.dumps({})
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        
        if response.status_code == 200:
            new_token = response.json().get("token")
            if new_token:
                current_token = new_token
                logger.info("✅ Token TTS renovado com sucesso!")
                return new_token
        else:
            logger.error(f"❌ Erro ao gerar token: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        logger.error(f"Erro ao gerar token Inworld: {e}")
    return None


def get_headers():
    global current_token
    logger.debug(f"🔑 Usando token: {current_token[:50]}..." if current_token else "❌ SEM TOKEN!")
    return {
        "Authorization": f"Bearer {current_token}",
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
    if filtro_idioma and filtro_idioma != 'all':
        filtered = []
        for v in voices:
            name = v.get('displayName', '')
            # Verifica se o nome da voz está no mapeamento e corresponde ao idioma
            voice_lang = VOICE_LANGUAGES.get(name, '')
            if voice_lang == filtro_idioma:
                filtered.append(v)
        voices = filtered
        logger.info(f"🔍 Filtradas {len(voices)} vozes ({IDIOMAS.get(filtro_idioma, filtro_idioma)})")
    
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
        logger.debug(f"📋 Headers: {dict(response.headers)}")
        try:
            logger.error(f"📋 Response: {response.text[:500]}")
        except:
            pass
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
        "• /idioma - Filtrar por idioma\n"
        "• /token - Renovar token\n\n"
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
        # Usa o mapeamento para mostrar o idioma
        lang_code = VOICE_LANGUAGES.get(name, '')
        lang_name = IDIOMAS.get(lang_code, '❓').split(' ')[-1] if lang_code else '❓'
        tags = voice.get('tags', [])[:2]
        
        # Mostra idioma (do mapeamento) ou tags
        info = lang_name if lang_name != '❓' else ', '.join(tags)
        
        texto += f"`{i}.` **{name}** ({info})\n"
    
    if len(voices) > 15:
        texto += f"\n_...e mais {len(voices) - 15} vozes_\n"
    
    texto += "\n💡 Use /idioma para filtrar por idioma"
    
    await update.message.reply_text(texto, parse_mode="Markdown")


async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renova o token Inworld manualmente"""
    await update.message.reply_text("🔄 Renovando token Inworld...")
    
    new_token = refresh_inworld_token()
    
    if new_token:
        await update.message.reply_text(
            "✅ **Token renovado com sucesso!**\n\n"
            f"📋 Token (primeiros 50 chars):\n`{new_token[:50]}...`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ **Falha ao renovar token!**\n\n"
            "Verifique se o FIREBASE_REFRESH_TOKEN está válido.",
            parse_mode="Markdown"
        )


async def settoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Define token manualmente copiado do F12"""
    global current_token
    
    if not context.args:
        await update.message.reply_text(
            "🔑 **Colar Token Manualmente**\n\n"
            "Use: `/settoken SEU_TOKEN_AQUI`\n\n"
            "Copie o token do F12 (Authorization header) e cole após o comando.",
            parse_mode="Markdown"
        )
        return
    
    new_token = context.args[0]
    
    # Validação básica
    if not new_token.startswith("eyJ"):
        await update.message.reply_text("❌ Token inválido! Deve começar com 'eyJ'")
        return
    
    current_token = new_token
    logger.info(f"🔑 Token atualizado manualmente!")
    
    await update.message.reply_text(
        "✅ **Token atualizado!**\n\n"
        f"📋 Token: `{new_token[:40]}...`\n\n"
        "Agora tente enviar um texto para testar!",
        parse_mode="Markdown"
    )

async def idioma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de seleção/filtro de vozes"""
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
        "🌍 **Filtrar vozes por idioma:**\n\n"
        "Selecione um idioma para ver as vozes disponíveis:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu para trocar voz"""
    user_id = update.effective_user.id
    current_voice = user_voices.get(user_id, DEFAULT_VOICE)
    current_name = current_voice.split('__')[-1] if '__' in current_voice else current_voice
    
    # Busca todas as vozes (sem filtro de idioma)
    voices = fetch_voices()[:9]  # Máximo 9 para caber nos botões
    
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
        # Selecionou filtro -> mostra vozes filtradas
        filtro = data.split(":")[1]
        voices = fetch_voices(filtro)
        
        if not voices:
            await query.edit_message_text(f"❌ Nenhuma voz encontrada para '{IDIOMAS.get(filtro, filtro)}'")
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
        
        filtro_nome = IDIOMAS.get(filtro, filtro)
        await query.edit_message_text(
            f"🎤 **{len(voices)} vozes ({filtro_nome}):**\n\nEscolha uma:",
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
║   Comandos: /voice /voices /idioma /token                    ║
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
    app.add_handler(CommandHandler("token", token_command))
    
    # Callbacks (botões)
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Mensagens de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_texto))
    
    logger.info("🚀 Bot iniciado!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
