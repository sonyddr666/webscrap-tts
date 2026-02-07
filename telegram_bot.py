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

# Import billing info para comando /uso
from billing_info import get_usage_text

# ============================================================
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
INWORLD_TOKEN = os.getenv("INWORLD_TOKEN")
WORKSPACE_ID = os.getenv("WORKSPACE_ID", "default--pb4bm1oowkem_r9ri2wiw")

BASE_URL = "https://api.inworld.ai"
DELAY_DELETE_SEGUNDOS = 50

# Firebase Token Refresh (do .env)
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyAPVBLVid0xPwjuU4Gmn_6_GyqxBq-SwQs")
FIREBASE_REFRESH_TOKEN = os.getenv("FIREBASE_REFRESH_TOKEN")

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
# Voz padrão
DEFAULT_VOICE = os.getenv("TTS_VOICE_ID", "default--pb4bm1oowkem_r9ri2wiw__sony")

# Modelos disponíveis
MODELOS = {
    'inworld-tts-1.5-max': '🚀 1.5 Max (Melhor Qualidade)',
    'inworld-tts-1.5-mini': '⚡ 1.5 Mini (Rápido)',
    'inworld-tts-1-max': 'v1 Max',
    'inworld-tts-1': 'v1 Standard'
}
DEFAULT_MODEL = 'inworld-tts-1.5-max'

# Modelo atual por usuário (user_id -> model_id)
user_models: Dict[int, str] = {}

# Configurações de áudio por usuário (user_id -> dict)
# { 'speed': 1.0, 'pitch': 0.0 }
user_settings: Dict[int, Dict[str, float]] = {}
DEFAULT_SPEED = 1.0
DEFAULT_PITCH = 1.1  # Temperature padrão do site


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
# VOICE CLONING - ESTADO
# ============================================================

# Estado do processo de clone por usuário
# user_id -> {'step': 'nome'|'idioma'|'audio', 'name': str, 'lang': str, 'files': []}
clone_sessions: Dict[int, dict] = {}

# Diretório para uploads de áudio
CLONE_UPLOAD_DIR = BASE_DIR / "clone_uploads"
CLONE_UPLOAD_DIR.mkdir(exist_ok=True)

# Idiomas para clone
CLONE_LANGUAGES = {
    'pt': ('PT_BR', '🇧🇷 Português'),
    'en': ('EN_US', '🇺🇸 English'),
    'es': ('ES_ES', '🇪🇸 Español'),
    'fr': ('FR_FR', '🇫🇷 Français'),
    'de': ('DE_DE', '🇩🇪 Deutsch'),
    'ja': ('JA_JP', '🇯🇵 日本語'),
    'ko': ('KO_KR', '🇰🇷 한국어'),
    'zh': ('ZH_CN', '🇨🇳 中文'),
    'ru': ('RU_RU', '🇷🇺 Русский'),
}

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


def generate_audio_direct(text: str, voice_id: str, filename: Path, model_id: str = DEFAULT_MODEL, speed: float = 1.0, pitch: float = 0.0) -> Optional[str]:
    """Gera áudio usando a API TTS"""
    url = f"{BASE_URL}/tts/v1/voice"
    
    payload = {
        "text": text,
        "voice_id": voice_id,
        "model_id": model_id,
        "audio_config": {
            "audio_encoding": "MP3",
            "speaking_rate": speed,
            "pitch": pitch,
            "sample_rate_hertz": 48000
        },
        "temperature": 1.0
    }
    
    logger.info(f"🎙️ Gerando ({model_id} | ⏩{speed} | 🎵{pitch}): '{text[:30]}...' com voz {voice_id[-15:]}")
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
# VOICE CLONING - FUNÇÕES DA API
# ============================================================

def audio_to_base64(audio_path: str) -> str:
    """Converte arquivo de áudio para Base64"""
    with open(audio_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def clone_voice_api(display_name: str, lang_code: str, audio_files: list, description: str = "") -> dict:
    """
    Clona uma voz usando a API Inworld
    
    Args:
        display_name: Nome da nova voz
        lang_code: Código do idioma (PT_BR, EN_US, etc.)
        audio_files: Lista de caminhos para arquivos de áudio
        description: Descrição opcional
    
    Returns:
        dict com dados da voz criada ou None
    """
    url = f"{BASE_URL}/voices/v1/workspaces/{WORKSPACE_ID}/voices:clone"
    
    samples = []
    total_size = 0
    
    for audio_path in audio_files:
        path = Path(audio_path)
        if not path.exists():
            logger.warning(f"⚠️ Arquivo não encontrado: {audio_path}")
            continue
        
        file_size = path.stat().st_size
        total_size += file_size
        
        logger.info(f"📁 Processando: {path.name} ({file_size/1024:.1f} KB)")
        
        samples.append({
            "title": path.name,
            "audioData": audio_to_base64(audio_path)
        })
    
    if not samples:
        logger.error("❌ Nenhum arquivo de áudio válido!")
        return None
    
    logger.info(f"📦 Total: {len(samples)} arquivos ({total_size/1024:.1f} KB)")
    
    payload = {
        "parent": f"workspaces/{WORKSPACE_ID}",
        "displayName": display_name,
        "langCode": lang_code,
        "description": description,
        "voiceSamples": samples
    }
    
    logger.info(f"🎭 Clonando voz '{display_name}' ({lang_code})...")
    logger.info(f"⏳ Isso pode demorar de 30 segundos a 3 minutos...")
    
    try:
        # Timeout alto porque clone demora!
        response = requests.post(url, headers=get_headers(), json=payload, timeout=300)
        
        if response.status_code == 200:
            data = response.json()
            voice = data.get("voice", {})
            logger.info(f"✅ Voz clonada: {voice.get('displayName')} - {voice.get('voiceId')}")
            return data
        else:
            logger.error(f"❌ Erro ao clonar: {response.status_code}")
            logger.error(response.text[:500])
            return None
    except Exception as e:
        logger.error(f"❌ Exceção no clone: {e}")
        return None


def list_custom_voices() -> list:
    """Lista apenas vozes clonadas (source: IVC)"""
    voices = fetch_voices()
    return [v for v in voices if v.get("source") == "IVC"]


# QUEUE WORKER
# ============================================================

async def queue_worker():
    """Processa a fila de áudio"""
    global audio_queue
    
    while True:
        try:
            # Aguarda a queue estar pronta
            if audio_queue is None:
                await asyncio.sleep(0.5)
                continue
                
            item = await audio_queue.get()
            update = item['update']
            texto = item['texto']
            voice_id = item['voice_id']
            model_id = item.get('model_id', DEFAULT_MODEL)
            user = update.effective_user
            
            # Obtém settings do usuário ou padrão
            settings = user_settings.get(user.id, {'speed': DEFAULT_SPEED, 'pitch': DEFAULT_PITCH})
            speed = settings.get('speed', DEFAULT_SPEED)
            pitch = settings.get('pitch', DEFAULT_PITCH)
            
            # Gera o áudio
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = OUTPUT_DIR / f"tg_{user.id}_{timestamp}.mp3"
            
            resultado = generate_audio_direct(texto, voice_id, filename, model_id, speed, pitch)
            
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
            await asyncio.sleep(1)  # Evita loop infinito de erros


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
    
    # Botões 3x3
    keyboard = [
        [
            InlineKeyboardButton("🎤 Vozes", callback_data="menu:voices"),
            InlineKeyboardButton("🔊 Voz", callback_data="menu:voice"),
            InlineKeyboardButton("🌍 Idioma", callback_data="menu:idioma"),
        ],
        [
            InlineKeyboardButton("🤖 Modelo", callback_data="menu:model"),
            InlineKeyboardButton("⏩ Speed", callback_data="menu:speed"),
            InlineKeyboardButton("🌡️ Temp", callback_data="menu:pitch"),
        ],
        [
            InlineKeyboardButton("🎭 Clonar", callback_data="menu:clonar"),
            InlineKeyboardButton("📋 Minhas", callback_data="menu:minhasvozes"),
            InlineKeyboardButton("🔑 Token", callback_data="menu:token"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎙️ **Bot TTS Inworld AI v4**\n\n"
        f"🎤 Voz: {voice_name}\n\n"
        "Envie texto para gerar áudio!\n"
        "Use os botões abaixo:",
        reply_markup=reply_markup,
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


async def uso_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra relatório de uso TTS"""
    await update.message.reply_text("📊 Obtendo dados de uso...")
    
    try:
        texto = get_usage_text()
        await update.message.reply_text(texto, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro /uso: {e}")
        await update.message.reply_text(f"❌ Erro ao obter dados: {e}")


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

async def speed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu para configurar velocidade"""
    user_id = update.effective_user.id
    current = user_settings.get(user_id, {}).get('speed', DEFAULT_SPEED)
    
    # Botões de velocidade (0.5 a 1.5, padrão 1.0)
    keyboard = [
        [
            InlineKeyboardButton("0.5", callback_data="speed:0.5"),
            InlineKeyboardButton("0.6", callback_data="speed:0.6"),
            InlineKeyboardButton("0.7", callback_data="speed:0.7"),
        ],
        [
            InlineKeyboardButton("0.8", callback_data="speed:0.8"),
            InlineKeyboardButton("0.9", callback_data="speed:0.9"),
            InlineKeyboardButton("✓ 1.0", callback_data="speed:1.0"),
        ],
        [
            InlineKeyboardButton("1.1", callback_data="speed:1.1"),
            InlineKeyboardButton("1.2", callback_data="speed:1.2"),
            InlineKeyboardButton("1.3", callback_data="speed:1.3"),
        ],
        [
            InlineKeyboardButton("1.4", callback_data="speed:1.4"),
            InlineKeyboardButton("1.5", callback_data="speed:1.5"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⏩ **Velocidade Atual:** `{current}`\n\n"
        "Valores: 0.5 (lento) → 1.5 (rápido)\n"
        "Padrão: 1.0\n\n"
        "Selecione:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def pitch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu para configurar temperatura (pitch)"""
    user_id = update.effective_user.id
    current = user_settings.get(user_id, {}).get('pitch', DEFAULT_PITCH)
    
    # Botões de temperatura (0.7 a 1.5, padrão 1.1)
    keyboard = [
        [
            InlineKeyboardButton("0.7", callback_data="pitch:0.7"),
            InlineKeyboardButton("0.8", callback_data="pitch:0.8"),
            InlineKeyboardButton("0.9", callback_data="pitch:0.9"),
        ],
        [
            InlineKeyboardButton("1.0", callback_data="pitch:1.0"),
            InlineKeyboardButton("✓ 1.1", callback_data="pitch:1.1"),
            InlineKeyboardButton("1.2", callback_data="pitch:1.2"),
        ],
        [
            InlineKeyboardButton("1.3", callback_data="pitch:1.3"),
            InlineKeyboardButton("1.4", callback_data="pitch:1.4"),
            InlineKeyboardButton("1.5", callback_data="pitch:1.5"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🌡️ **Temperatura Atual:** `{current}`\n\n"
        "Valores: 0.7 (frio) → 1.5 (quente)\n"
        "Padrão: 1.1\n\n"
        "Selecione:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu para trocar modelo TTS"""
    user_id = update.effective_user.id
    current_model = user_models.get(user_id, DEFAULT_MODEL)
    
    keyboard = []
    for model_id, name in MODELOS.items():
        prefix = "✅ " if model_id == current_model else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"model:{model_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🤖 **Modelo Atual:** `{MODELOS.get(current_model, current_model)}`\n\n"
        "Selecione o modelo de geração:",
        reply_markup=reply_markup,
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
# VOICE CLONING - COMANDOS
# ============================================================

async def clonar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia processo de clone de voz"""
    user_id = update.effective_user.id
    
    # Limpa sessão anterior se existir
    if user_id in clone_sessions:
        del clone_sessions[user_id]
    
    # Cria nova sessão
    clone_sessions[user_id] = {
        'step': 'nome',
        'name': None,
        'lang': None,
        'lang_code': None,
        'files': []
    }
    
    await update.message.reply_text(
        "🎭 **CLONAR VOZ**\n\n"
        "Vou guiar você pelo processo de clonagem!\n\n"
        "**Passo 1/3:** Digite o nome para a nova voz:\n\n"
        "_Exemplo: MinhaVoz, VozCustomizada, etc._\n\n"
        "Use /cancelar para abortar.",
        parse_mode="Markdown"
    )


async def minhasvozes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista vozes clonadas do usuário"""
    await update.message.reply_text("🔍 Buscando suas vozes clonadas...")
    
    voices = list_custom_voices()
    
    if not voices:
        await update.message.reply_text(
            "📭 **Nenhuma voz clonada encontrada!**\n\n"
            "Use /clonar para criar sua primeira voz.",
            parse_mode="Markdown"
        )
        return
    
    # Cria botões para selecionar voz clonada
    keyboard = []
    row = []
    
    for voice in voices[:12]:
        name = voice.get('displayName', '?')[:12]
        voice_id = voice.get('voiceId', '')
        
        row.append(InlineKeyboardButton(
            f"🎭 {name}",
            callback_data=f"voice:{voice_id}"
        ))
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Mensagem simplificada (sem IDs para evitar erro de Markdown)
    texto = f"🎭 **Suas Vozes Clonadas ({len(voices)}):**\n\n"
    for v in voices[:10]:
        texto += f"• {v.get('displayName')} ({v.get('langCode')})\n"
    
    if len(voices) > 10:
        texto += f"\n_...e mais {len(voices) - 10} vozes_\n"
    
    texto += "\n💡 Clique para selecionar:"
    
    await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")


async def cancelar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela processo de clone em andamento"""
    user_id = update.effective_user.id
    
    if user_id in clone_sessions:
        # Limpa arquivos temporários
        session = clone_sessions[user_id]
        for file_path in session.get('files', []):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        
        del clone_sessions[user_id]
        await update.message.reply_text("❌ Processo de clonagem cancelado.")
    else:
        await update.message.reply_text("ℹ️ Nenhum processo de clonagem em andamento.")


async def processar_clone_steps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Processa passos do clone de voz quando usuário está em sessão
    Retorna True se processou mensagem de clone, False caso contrário
    """
    user_id = update.effective_user.id
    
    if user_id not in clone_sessions:
        return False
    
    session = clone_sessions[user_id]
    step = session.get('step')
    text = update.message.text.strip() if update.message.text else None
    
    # PASSO 1: Nome da voz
    if step == 'nome' and text:
        # Valida nome (sem espaços, caracteres especiais)
        nome_limpo = "".join(c for c in text if c.isalnum() or c == '_')[:20]
        
        if len(nome_limpo) < 2:
            await update.message.reply_text(
                "⚠️ Nome muito curto ou inválido.\n"
                "Use apenas letras, números e _ (mínimo 2 caracteres)."
            )
            return True
        
        session['name'] = nome_limpo
        session['step'] = 'idioma'
        
        # Menu de idiomas
        keyboard = []
        row = []
        for code, (lang_code, lang_name) in CLONE_LANGUAGES.items():
            row.append(InlineKeyboardButton(lang_name, callback_data=f"clone_lang:{code}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Nome: **{nome_limpo}**\n\n"
            "**Passo 2/3:** Selecione o idioma da voz:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return True
    
    return False


async def processar_audio_clone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa uploads de áudio para clone de voz"""
    user_id = update.effective_user.id
    
    if user_id not in clone_sessions:
        return
    
    session = clone_sessions[user_id]
    
    if session.get('step') != 'audio':
        return
    
    # Obtém arquivo de áudio (voice ou audio ou document)
    audio_file = None
    file_name = None
    
    if update.message.voice:
        audio_file = update.message.voice
        file_name = f"voice_{user_id}_{len(session['files'])}.ogg"
    elif update.message.audio:
        audio_file = update.message.audio
        file_name = update.message.audio.file_name or f"audio_{user_id}_{len(session['files'])}.mp3"
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type and 'audio' in doc.mime_type:
            audio_file = doc
            file_name = doc.file_name or f"doc_{user_id}_{len(session['files'])}.mp3"
    
    if not audio_file:
        return
    
    try:
        # Baixa o arquivo
        file = await audio_file.get_file()
        file_path = CLONE_UPLOAD_DIR / file_name
        await file.download_to_drive(file_path)
        
        session['files'].append(str(file_path))
        num_files = len(session['files'])
        
        await update.message.reply_text(
            f"✅ Áudio {num_files} recebido!\n\n"
            f"📁 Arquivos: {num_files}\n\n"
            "Envie mais áudios ou clique em **Finalizar** para clonar:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎭 Finalizar e Clonar", callback_data="clone_finish")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="clone_cancel")]
            ]),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Erro ao baixar áudio: {e}")
        await update.message.reply_text(f"❌ Erro ao processar áudio: {e}")


# ============================================================
# HANDLER - CALLBACKS (BOTÕES)
# ============================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques nos botões inline"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # ============================================================
    # MENU DO /START
    # ============================================================
    
    if data.startswith("menu:"):
        menu_action = data.split(":")[1]
        
        if menu_action == "voices":
            # Lista vozes
            voices = fetch_voices()
            if not voices:
                await query.edit_message_text("❌ Erro ao carregar vozes.")
                return
            texto = "🎤 **Vozes Disponíveis:**\n\n"
            for i, v in enumerate(voices[:15], 1):
                texto += f"{i}. {v.get('displayName')}\n"
            texto += "\nUse /voice para selecionar."
            await query.edit_message_text(texto, parse_mode="Markdown")
            return
        
        elif menu_action == "voice":
            # Menu de seleção de voz
            current_voice = user_voices.get(user_id, DEFAULT_VOICE)
            voices = fetch_voices()[:9]
            if not voices:
                await query.edit_message_text("❌ Erro ao carregar vozes.")
                return
            
            keyboard = []
            row = []
            for voice in voices:
                name = voice.get('displayName', '?')[:12]
                voice_id = voice.get('voiceId') or voice.get('name', '')
                prefix = "✓ " if voice_id == current_voice else ""
                row.append(InlineKeyboardButton(f"{prefix}{name}", callback_data=f"voice:{voice_id}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("« Voltar", callback_data="menu:back")])
            
            await query.edit_message_text(
                "🔊 **Selecione uma voz:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        elif menu_action == "idioma":
            # Menu de idiomas
            keyboard = []
            row = []
            for code, name in IDIOMAS.items():
                row.append(InlineKeyboardButton(name, callback_data=f"idioma:{code}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("« Voltar", callback_data="menu:back")])
            
            await query.edit_message_text(
                "🌍 **Filtrar por idioma:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        elif menu_action == "model":
            # Menu de modelos
            current_model = user_models.get(user_id, DEFAULT_MODEL)
            keyboard = []
            for model_id, name in MODELOS.items():
                prefix = "✅ " if model_id == current_model else ""
                keyboard.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"model:{model_id}")])
            keyboard.append([InlineKeyboardButton("« Voltar", callback_data="menu:back")])
            
            await query.edit_message_text(
                "🤖 **Selecione o modelo:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        elif menu_action == "speed":
            # Menu de velocidade
            current = user_settings.get(user_id, {}).get('speed', DEFAULT_SPEED)
            keyboard = [
                [
                    InlineKeyboardButton("0.5", callback_data="speed:0.5"),
                    InlineKeyboardButton("0.6", callback_data="speed:0.6"),
                    InlineKeyboardButton("0.7", callback_data="speed:0.7"),
                ],
                [
                    InlineKeyboardButton("0.8", callback_data="speed:0.8"),
                    InlineKeyboardButton("0.9", callback_data="speed:0.9"),
                    InlineKeyboardButton("✓ 1.0", callback_data="speed:1.0"),
                ],
                [
                    InlineKeyboardButton("1.1", callback_data="speed:1.1"),
                    InlineKeyboardButton("1.2", callback_data="speed:1.2"),
                    InlineKeyboardButton("1.3", callback_data="speed:1.3"),
                ],
                [
                    InlineKeyboardButton("1.4", callback_data="speed:1.4"),
                    InlineKeyboardButton("1.5", callback_data="speed:1.5"),
                    InlineKeyboardButton("« Voltar", callback_data="menu:back"),
                ]
            ]
            await query.edit_message_text(
                f"⏩ **Speed atual:** {current}\n\n0.5 (lento) → 1.5 (rápido)",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        elif menu_action == "pitch":
            # Menu de temperatura
            current = user_settings.get(user_id, {}).get('pitch', DEFAULT_PITCH)
            keyboard = [
                [
                    InlineKeyboardButton("0.7", callback_data="pitch:0.7"),
                    InlineKeyboardButton("0.8", callback_data="pitch:0.8"),
                    InlineKeyboardButton("0.9", callback_data="pitch:0.9"),
                ],
                [
                    InlineKeyboardButton("1.0", callback_data="pitch:1.0"),
                    InlineKeyboardButton("✓ 1.1", callback_data="pitch:1.1"),
                    InlineKeyboardButton("1.2", callback_data="pitch:1.2"),
                ],
                [
                    InlineKeyboardButton("1.3", callback_data="pitch:1.3"),
                    InlineKeyboardButton("1.4", callback_data="pitch:1.4"),
                    InlineKeyboardButton("1.5", callback_data="pitch:1.5"),
                ],
                [InlineKeyboardButton("« Voltar", callback_data="menu:back")]
            ]
            await query.edit_message_text(
                f"🌡️ **Temperatura atual:** {current}\n\n0.7 (frio) → 1.5 (quente)",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        elif menu_action == "clonar":
            # Inicia clone
            if user_id in clone_sessions:
                del clone_sessions[user_id]
            clone_sessions[user_id] = {'step': 'nome', 'files': []}
            await query.edit_message_text(
                "🎭 **CLONAR VOZ**\n\n"
                "**Passo 1/3:** Digite o nome para a nova voz:\n\n"
                "_Exemplo: MinhaVoz, VozCustomizada_\n\n"
                "Use /cancelar para abortar.",
                parse_mode="Markdown"
            )
            return
        
        elif menu_action == "minhasvozes":
            # Lista vozes clonadas
            voices = list_custom_voices()
            if not voices:
                await query.edit_message_text(
                    "📭 Nenhuma voz clonada!\n\nUse 🎭 Clonar para criar."
                )
                return
            
            keyboard = []
            row = []
            for voice in voices[:12]:
                name = voice.get('displayName', '?')[:12]
                voice_id = voice.get('voiceId', '')
                row.append(InlineKeyboardButton(f"🎭 {name}", callback_data=f"voice:{voice_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("« Voltar", callback_data="menu:back")])
            
            texto = f"🎭 **Vozes Clonadas ({len(voices)}):**\n\n"
            for v in voices[:5]:
                texto += f"• {v.get('displayName')}\n"
            
            await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        
        elif menu_action == "token":
            # Renova token
            await query.edit_message_text("🔄 Renovando token...")
            new_token = refresh_inworld_token()
            if new_token:
                await query.edit_message_text("✅ Token renovado com sucesso!")
            else:
                await query.edit_message_text("❌ Falha ao renovar token!")
            return
        
        elif menu_action == "back":
            # Volta ao menu principal
            voice = user_voices.get(user_id, DEFAULT_VOICE)
            voice_name = voice.split('__')[-1] if '__' in voice else voice
            
            keyboard = [
                [
                    InlineKeyboardButton("🎤 Vozes", callback_data="menu:voices"),
                    InlineKeyboardButton("🔊 Voz", callback_data="menu:voice"),
                    InlineKeyboardButton("🌍 Idioma", callback_data="menu:idioma"),
                ],
                [
                    InlineKeyboardButton("🤖 Modelo", callback_data="menu:model"),
                    InlineKeyboardButton("⏩ Speed", callback_data="menu:speed"),
                    InlineKeyboardButton("🌡️ Temp", callback_data="menu:pitch"),
                ],
                [
                    InlineKeyboardButton("🎭 Clonar", callback_data="menu:clonar"),
                    InlineKeyboardButton("📋 Minhas", callback_data="menu:minhasvozes"),
                    InlineKeyboardButton("🔑 Token", callback_data="menu:token"),
                ],
            ]
            await query.edit_message_text(
                f"🎙️ **Bot TTS Inworld AI v4**\n\n"
                f"🎤 Voz: {voice_name}\n\n"
                "Envie texto para gerar áudio!\n"
                "Use os botões abaixo:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
    
    if data.startswith("model:"):
        # Selecionou modelo
        model_id = data.split(":", 1)[1]
        if model_id in MODELOS:
            user_models[user_id] = model_id
            await query.edit_message_text(
                f"✅ **Modelo alterado!**\n\n🤖 Novo modelo: `{MODELOS[model_id]}`",
                parse_mode="Markdown"
            )
            logger.info(f"🤖 {query.from_user.first_name} trocou modelo para: {model_id}")
        return

    if data.startswith("speed:"):
        # Alterou velocidade
        valor = float(data.split(":")[1])
        if user_id not in user_settings: user_settings[user_id] = {}
        user_settings[user_id]['speed'] = valor
        await query.edit_message_text(
            f"✅ **Velocidade definida!**\n\n⏩ Valor: `{valor}`",
            parse_mode="Markdown"
        )
        return

    if data.startswith("pitch:"):
        # Alterou tom
        valor = float(data.split(":")[1])
        if user_id not in user_settings: user_settings[user_id] = {}
        user_settings[user_id]['pitch'] = valor
        await query.edit_message_text(
            f"✅ **Tom definido!**\n\n🎵 Valor: `{valor}`",
            parse_mode="Markdown"
        )
        return

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
    # VOICE CLONING CALLBACKS
    # ============================================================
    
    elif data.startswith("clone_lang:"):
        # Selecionou idioma para clone
        lang_code_short = data.split(":")[1]
        
        if user_id not in clone_sessions:
            await query.edit_message_text("❌ Sessão expirada. Use /clonar novamente.")
            return
        
        session = clone_sessions[user_id]
        
        if lang_code_short in CLONE_LANGUAGES:
            lang_code, lang_name = CLONE_LANGUAGES[lang_code_short]
            session['lang'] = lang_code_short
            session['lang_code'] = lang_code
            session['step'] = 'audio'
            
            await query.edit_message_text(
                f"✅ Nome: **{session['name']}**\n"
                f"✅ Idioma: **{lang_name}**\n\n"
                "**Passo 3/3:** Envie os arquivos de áudio para clonar!\n\n"
                "📎 Formatos aceitos: MP3, WAV, OGG\n"
                "⏱️ Duração mínima: 30 segundos total\n"
                "📁 Envie quantos áudios quiser\n\n"
                "_Quando terminar, clique em Finalizar._",
                parse_mode="Markdown"
            )
    
    elif data == "clone_finish":
        # Finalizar clone
        if user_id not in clone_sessions:
            await query.edit_message_text("❌ Sessão expirada. Use /clonar novamente.")
            return
        
        session = clone_sessions[user_id]
        
        if len(session.get('files', [])) == 0:
            await query.edit_message_text(
                "⚠️ Nenhum áudio enviado!\n\n"
                "Envie pelo menos 1 arquivo de áudio antes de finalizar.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancelar", callback_data="clone_cancel")]
                ])
            )
            return
        
        await query.edit_message_text(
            f"🔄 **CLONANDO VOZ...**\n\n"
            f"📛 Nome: {session['name']}\n"
            f"🌍 Idioma: {session['lang_code']}\n"
            f"📁 Arquivos: {len(session['files'])}\n\n"
            "⏳ **AGUARDE!** Este processo pode demorar:\n"
            "   • 30 segundos a 3 minutos\n"
            "   • Depende do tamanho dos áudios\n\n"
            "☕ Relaxe enquanto a IA processa sua voz..."
        )
        
        # Executa clone
        result = clone_voice_api(
            display_name=session['name'],
            lang_code=session['lang_code'],
            audio_files=session['files']
        )
        
        # Limpa arquivos temporários
        for file_path in session.get('files', []):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        
        # Remove sessão
        del clone_sessions[user_id]
        
        if result:
            voice = result.get("voice", {})
            voice_id = voice.get("voiceId", "")
            
            # Define a voz clonada como voz atual
            user_voices[user_id] = voice_id
            
            await query.edit_message_text(
                "🎉 **VOZ CLONADA COM SUCESSO!**\n\n"
                f"📛 Nome: {voice.get('displayName')}\n"
                f"🌍 Idioma: {voice.get('langCode')}\n\n"
                "✅ Esta voz já foi selecionada!\n"
                "Envie um texto para testar."
            )
            logger.info(f"🎭 {query.from_user.first_name} clonou voz: {voice.get('displayName')}")
        else:
            await query.edit_message_text(
                "❌ **Erro ao clonar voz!**\n\n"
                "Possíveis causas:\n"
                "• Token expirado (use /token)\n"
                "• Áudio muito curto\n"
                "• Formato não suportado\n\n"
                "Tente novamente com /clonar",
                parse_mode="Markdown"
            )
    
    elif data == "clone_cancel":
        # Cancelar clone
        if user_id in clone_sessions:
            session = clone_sessions[user_id]
            for file_path in session.get('files', []):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
            del clone_sessions[user_id]
        
        await query.edit_message_text("❌ Clonagem cancelada.")


# ============================================================
# HANDLER - MENSAGENS DE TEXTO
# ============================================================

async def processar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona texto à fila de processamento"""
    global audio_queue
    
    # Verifica se está em processo de clone
    if await processar_clone_steps(update, context):
        return
    
    texto = update.message.text.strip()
    if not texto:
        return
    
    if len(texto) > 2000:
        await update.message.reply_text("⚠️ Texto muito longo. Máximo: 2000 caracteres.")
        texto = texto[:2000]
    
    user = update.effective_user
    voice_id = user_voices.get(user.id, DEFAULT_VOICE)
    model_id = user_models.get(user.id, DEFAULT_MODEL)
    
    logger.info(f"📩 {user.first_name}: {texto[:40]}...")
    
    # Adiciona à fila
    queue_size = audio_queue.qsize()
    
    await audio_queue.put({
        'update': update,
        'texto': texto,
        'voice_id': voice_id,
        'model_id': model_id
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
║   🤖 TELEGRAM TTS BOT v4 - COM VOICE CLONING                 ║
║                                                              ║
║   Comandos: /voice /voices /idioma /token /model             ║
║             /clonar /minhasvozes /cancelar                   ║
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
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("speed", speed_command))
    app.add_handler(CommandHandler("pitch", pitch_command))
    app.add_handler(CommandHandler("token", token_command))
    app.add_handler(CommandHandler("uso", uso_command))
    
    # Comandos de Voice Cloning
    app.add_handler(CommandHandler("clonar", clonar_command))
    app.add_handler(CommandHandler("minhasvozes", minhasvozes_command))
    app.add_handler(CommandHandler("cancelar", cancelar_command))
    
    # Callbacks (botões)
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Mensagens de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_texto))
    
    # Handler de áudio para clone de voz
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.AUDIO, processar_audio_clone))
    
    logger.info("🚀 Bot iniciado!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
