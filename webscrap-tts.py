# Inworld AI TTS Scraper v2.0 - Versão Profissional
# =====================================================
# Inclui: Auto-refresh de token, Retry inteligente, Anti-detecção,
# Filtro por idioma, Logging completo, Estatísticas, e mais.

import requests
import json
import base64
import time
import random
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# ============================================================
# CONFIGURAÇÕES
# ============================================================

# Diretórios
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

# Criar diretório de saída se não existir
OUTPUT_DIR.mkdir(exist_ok=True)

# Configurações da API Inworld (Endpoints internos - Engenharia Reversa)
WORKSPACE_ID = os.getenv("WORKSPACE_ID", "default--pb4bm1oowkem_r9ri2wiw")
BASE_URL = "https://api.inworld.ai"

# Token inicial (será atualizado pelo cache ou manualmente)
# Carrega do .env (INWORLD_TOKEN) ou usa string vazia/None se não encontrado
TOKEN = os.getenv("INWORLD_TOKEN")

# Mapa de idiomas suportados pela Inworld TTS-1.5
IDIOMAS = {
    'pt': '🇧🇷 Português',
    'en': '🇺🇸 English',
    'es': '🇪🇸 Español',
    'fr': '🇫🇷 Français',
    'de': '🇩🇪 Deutsch',
    'it': '🇮🇹 Italiano',
    'nl': '🇳🇱 Nederlands',
    'pl': '🇵🇱 Polski',
    'ru': '🇷🇺 Русский',
    'zh': '🇨🇳 中文',
    'ja': '🇯🇵 日本語',
    'ko': '🇰🇷 한국어',
    'hi': '🇮🇳 हिन्दी',
    'ar': '🇸🇦 العربية',
    'he': '🇮🇱 עברית'
}

# Limite de caracteres da API Inworld
MAX_CARACTERES = 2000

# User-Agents para rotação (Anti-detecção)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
]

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# ESTATÍSTICAS
# ============================================================

class ScraperStats:
    """Monitora estatísticas de uso do scraper"""
    def __init__(self):
        self.requisicoes = 0
        self.sucessos = 0
        self.erros_401 = 0
        self.erros_429 = 0
        self.erros_outros = 0
        self.total_bytes = 0
        self.inicio = datetime.now()
    
    def relatorio(self):
        duracao = datetime.now() - self.inicio
        taxa_sucesso = (self.sucessos / self.requisicoes * 100) if self.requisicoes > 0 else 0
        
        print("\n" + "="*50)
        print("📊 ESTATÍSTICAS DA SESSÃO")
        print("="*50)
        print(f"  ⏱️  Duração: {duracao}")
        print(f"  📨 Requisições: {self.requisicoes}")
        print(f"  ✅ Sucessos: {self.sucessos} ({taxa_sucesso:.1f}%)")
        print(f"  🔑 Erros 401 (token): {self.erros_401}")
        print(f"  ⏳ Erros 429 (rate limit): {self.erros_429}")
        print(f"  ❌ Outros erros: {self.erros_outros}")
        print(f"  💾 Dados transferidos: {self.total_bytes / 1024:.2f} KB")
        print("="*50 + "\n")

stats = ScraperStats()

# ============================================================
# SISTEMA DE TOKEN (Cache + Validação JWT)
# ============================================================

def decodificar_jwt(token):
    """Decodifica payload do JWT para verificar expiração"""
    try:
        payload_b64 = token.split('.')[1]
        # Adiciona padding se necessário
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload
    except Exception as e:
        logger.warning(f"Erro ao decodificar JWT: {e}")
        return None

def verificar_token_valido(token):
    """Verifica se o token JWT ainda é válido"""
    payload = decodificar_jwt(token)
    if not payload:
        return False, "Não foi possível decodificar o token"
    
    exp_timestamp = payload.get('exp')
    if not exp_timestamp:
        return True, "Token sem data de expiração (assumindo válido)"
    
    exp_date = datetime.fromtimestamp(exp_timestamp)
    agora = datetime.now()
    tempo_restante = exp_date - agora
    
    if tempo_restante.total_seconds() < 0:
        return False, f"Token EXPIRADO há {abs(tempo_restante)}"
    elif tempo_restante.total_seconds() < 3600:  # Menos de 1 hora
        return True, f"⚠️ Token expira em {tempo_restante} (considere renovar)"
    else:
        dias = tempo_restante.days
        horas = tempo_restante.seconds // 3600
        return True, f"✅ Token válido por {dias}d {horas}h"

def obter_token():
    """Obtém token das variáveis de ambiente"""
    global TOKEN
    
    # Valida token do .env
    valido, msg = verificar_token_valido(TOKEN)
    logger.info(f"Token (.env): {msg}")
    
    if not valido:
        logger.error("❌ TOKEN EXPIRADO OU NÃO ENCONTRADO! Atualize o arquivo .env")
        print("\n" + "="*60)
        print("⚠️  TOKEN EXPIRADO OU AUSENTE!")
        print("="*60)
        print("Para atualizar:")
        print("1. Acesse https://studio.inworld.ai/")
        print("2. Abra DevTools (F12) > Network")
        print("3. Copie o header 'Authorization: Bearer ey...'")
        print("4. Atualize a variável INWORLD_TOKEN no arquivo .env")
        print("="*60 + "\n")
        return None
    
    return TOKEN

# ============================================================
# HEADERS COM ANTI-DETECÇÃO
# ============================================================

def get_headers():
    """Gera headers realistas com User-Agent rotativo"""
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://platform.inworld.ai",
        "Referer": "https://platform.inworld.ai/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Chromium";v="144", "Google Chrome";v="144"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

def delay_humano(min_seg=1.0, max_seg=2.5):
    """Pausa aleatória simulando comportamento humano"""
    tempo = random.uniform(min_seg, max_seg)
    time.sleep(tempo)

# ============================================================
# DECORATOR DE RETRY COM BACKOFF EXPONENCIAL
# ============================================================

def retry_com_backoff(max_tentativas=3, backoff_factor=2):
    """Decorator para retry automático com exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            ultima_excecao = None
            
            for tentativa in range(max_tentativas):
                try:
                    resultado = func(*args, **kwargs)
                    return resultado
                    
                except requests.exceptions.HTTPError as e:
                    stats.requisicoes += 1
                    ultima_excecao = e
                    status = e.response.status_code
                    
                    if status == 401:
                        stats.erros_401 += 1
                        logger.error("❌ Token expirado ou inválido (401)")
                        return None  # Não faz retry para 401
                    
                    elif status == 429:
                        stats.erros_429 += 1
                        tempo_espera = backoff_factor ** tentativa * 10
                        logger.warning(f"⏳ Rate limit (429). Aguardando {tempo_espera}s...")
                        time.sleep(tempo_espera)
                        continue
                    
                    elif status == 403:
                        stats.erros_outros += 1
                        logger.error("🚫 Acesso negado (403). Possível detecção de bot.")
                        return None
                    
                    else:
                        stats.erros_outros += 1
                        logger.warning(f"Erro HTTP {status}. Tentativa {tentativa+1}/{max_tentativas}")
                        time.sleep(backoff_factor ** tentativa)
                        continue
                
                except requests.exceptions.Timeout:
                    stats.erros_outros += 1
                    logger.warning(f"⏱️ Timeout. Tentativa {tentativa+1}/{max_tentativas}")
                    time.sleep(backoff_factor ** tentativa)
                    continue
                
                except Exception as e:
                    stats.erros_outros += 1
                    ultima_excecao = e
                    logger.warning(f"Erro: {e}. Tentativa {tentativa+1}/{max_tentativas}")
                    time.sleep(backoff_factor ** tentativa)
                    continue
            
            # Todas as tentativas falharam
            logger.error(f"❌ Falha após {max_tentativas} tentativas: {ultima_excecao}")
            return None
        
        return wrapper
    return decorator

# ============================================================
# FUNÇÕES DA API
# ============================================================

@retry_com_backoff(max_tentativas=3)
def list_voices(filtro_idioma=None):
    """Lista vozes disponíveis, opcionalmente filtradas por idioma"""
    url = f"{BASE_URL}/voices/v1/workspaces/{WORKSPACE_ID}/voices"
    
    # Adiciona filtro de idioma se especificado
    params = {}
    if filtro_idioma:
        params['filter'] = f'language={filtro_idioma}'
    
    logger.info(f"Listando vozes... (filtro: {filtro_idioma or 'nenhum'})")
    delay_humano(0.5, 1.0)
    
    response = requests.get(url, headers=get_headers(), params=params, timeout=30)
    response.raise_for_status()
    
    stats.requisicoes += 1
    stats.sucessos += 1
    stats.total_bytes += len(response.content)
    
    voices = response.json().get('voices', [])
    
    if filtro_idioma:
        logger.info(f"Encontradas {len(voices)} vozes em {IDIOMAS.get(filtro_idioma, filtro_idioma)}")
    else:
        logger.info(f"Encontradas {len(voices)} vozes no total")
    
    return voices

@retry_com_backoff(max_tentativas=3)
def generate_audio(text, voice_id, filename=None):
    """Gera áudio usando a API TTS"""
    url = f"{BASE_URL}/tts/v1/voice"
    
    # Gera nome de arquivo automático se não fornecido
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitiza o texto para usar no nome
        safe_text = "".join(c for c in text[:25] if c.isalnum() or c in (' ', '_')).strip()
        safe_text = safe_text.replace(' ', '_')
        filename = OUTPUT_DIR / f"audio_{timestamp}_{safe_text}.mp3"
    else:
        filename = Path(filename)
    
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
    logger.debug(f"voice_id: {voice_id}")
    
    delay_humano()
    
    response = requests.post(url, headers=get_headers(), json=payload, timeout=60)
    response.raise_for_status()
    
    stats.requisicoes += 1
    stats.sucessos += 1
    stats.total_bytes += len(response.content)
    
    content_type = response.headers.get('Content-Type', '')
    logger.debug(f"Content-Type: {content_type}")
    
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
        # Bytes brutos (menos comum)
        with open(filename, "wb") as f:
            f.write(response.content)
        logger.info(f"✅ Áudio salvo: {filename} (raw, {len(response.content)/1024:.1f} KB)")
        return str(filename)

# ============================================================
# INTERFACE DE USUÁRIO
# ============================================================

def exibir_vozes(voices, max_exibir=15):
    """Exibe lista de vozes formatada"""
    print("\n" + "="*70)
    print(f"{'#':<4} {'Nome':<20} {'Idiomas':<15} {'Tags'}")
    print("="*70)
    
    for i, voice in enumerate(voices[:max_exibir], 1):
        display_name = voice.get('displayName', 'Sem nome')[:18]
        languages = ', '.join(voice.get('languages', []))[:12]
        tags = voice.get('tags', [])
        tags_str = ', '.join(tags[:3])
        if len(tags) > 3:
            tags_str += '...'
        
        print(f"{i:<4} {display_name:<20} {languages:<15} {tags_str}")
    
    if len(voices) > max_exibir:
        print(f"\n... e mais {len(voices) - max_exibir} vozes")
    
    print("="*70)

def escolher_idioma():
    """Menu interativo para escolher idioma"""
    print("\n╔════════════════════════════════════════╗")
    print("║       ESCOLHA O IDIOMA DAS VOZES       ║")
    print("╚════════════════════════════════════════╝\n")
    
    idiomas_lista = list(IDIOMAS.items())
    
    # Exibe em 3 colunas
    for i in range(0, len(idiomas_lista), 3):
        linha = ""
        for j in range(3):
            if i + j < len(idiomas_lista):
                codigo, nome = idiomas_lista[i + j]
                linha += f"{i+j+1:2}. {nome:<18}"
        print(linha)
    
    print(f"\n 0. Todas as línguas (sem filtro)")
    
    while True:
        escolha = input("\n📍 Digite o número: ").strip()
        
        if escolha == '0' or escolha == '':
            return None
        
        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(idiomas_lista):
                codigo = idiomas_lista[idx][0]
                print(f"✅ Selecionado: {IDIOMAS[codigo]}")
                return codigo
        except ValueError:
            pass
        
        print("❌ Opção inválida. Tente novamente.")

def escolher_voz(voices):
    """Menu interativo para escolher voz"""
    if not voices:
        logger.error("Nenhuma voz disponível.")
        return None
    
    exibir_vozes(voices)
    
    print(f"\nTotal: {len(voices)} vozes disponíveis")
    escolha = input(f"📍 Escolha o número da voz (1-{min(len(voices), 15)}, Enter=1): ").strip()
    
    if not escolha:
        voice = voices[0]
    else:
        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(voices):
                voice = voices[idx]
            else:
                print("⚠️ Número fora do range. Usando primeira voz.")
                voice = voices[0]
        except ValueError:
            print("⚠️ Entrada inválida. Usando primeira voz.")
            voice = voices[0]
    
    display_name = voice.get('displayName', 'Desconhecida')
    voice_id = voice.get('voiceId') or voice.get('name') or voice.get('id')
    print(f"\n🎤 Voz selecionada: {display_name}")
    
    return voice

# ============================================================
# MAIN
# ============================================================

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🎙️  INWORLD AI TTS SCRAPER v2.0                           ║
║                                                              ║
║   Engenharia Reversa da API Inworld                          ║
║   Suporte a 15 idiomas • Modelo TTS-1.5-Max • 48kHz          ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # 1. Verifica/carrega token
    token = obter_token()
    if not token:
        print("❌ Impossível continuar sem token válido.")
        return
    
    # 2. Escolhe idioma
    codigo_idioma = escolher_idioma()
    
    # 3. Lista vozes
    voices = list_voices(filtro_idioma=codigo_idioma)
    if not voices:
        print("❌ Nenhuma voz encontrada. Verifique o token ou o filtro de idioma.")
        return
    
    # 4. Escolhe voz
    voice = escolher_voz(voices)
    if not voice:
        return
    
    voice_id = voice.get('voiceId') or voice.get('name') or voice.get('id')
    
    # 5. Loop de geração
    print("\n" + "─"*60)
    print("💬 Digite textos para gerar áudio")
    print("   Comandos: 'sair', 'stats', 'voz'")
    print("─"*60)
    
    while True:
        try:
            text = input("\n📝 Texto: ").strip()
            
            if not text:
                continue
            
            cmd = text.lower()
            
            if cmd in ['sair', 'exit', 'quit', 'q']:
                stats.relatorio()
                print("👋 Até logo!")
                break
            
            elif cmd == 'stats':
                stats.relatorio()
                continue
            
            elif cmd == 'voz':
                voice = escolher_voz(voices)
                if voice:
                    voice_id = voice.get('voiceId') or voice.get('name') or voice.get('id')
                continue
            
            # Verifica limite de caracteres
            if len(text) > MAX_CARACTERES:
                print(f"   ⚠️ Texto muito longo! ({len(text)}/{MAX_CARACTERES} caracteres)")
                print(f"   Truncando para {MAX_CARACTERES} caracteres...")
                text = text[:MAX_CARACTERES]
            
            # Gera áudio
            resultado = generate_audio(text, voice_id)
            
            if resultado:
                print(f"   Arquivo: {resultado}")
            else:
                print("   ❌ Falha na geração. Verifique o log para detalhes.")
        
        except KeyboardInterrupt:
            print("\n\n⚠️ Interrompido pelo usuário.")
            stats.relatorio()
            break

if __name__ == "__main__":
    main()
