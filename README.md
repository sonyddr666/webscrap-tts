# 🎙️ Inworld AI TTS Scraper & Telegram Bot

Bot de Telegram que usa engenharia reversa da API TTS da Inworld AI para gerar áudio de alta qualidade com vozes neurais em 15+ idiomas.

---

## 🚀 Funcionalidades

| Feature | Descrição |
|:--------|:----------|
| 🤖 **Bot Telegram** | Interface completa via Telegram com comandos interativos |
| 🔄 **Auto-Renovação de Token** | Renova automaticamente usando Firebase + Portal endpoint |
| 🌍 **15+ Idiomas** | Português, English, Español, Français, Deutsch, 日本語, 한국어, 中文, Русский e mais |
| 🎤 **50+ Vozes** | Vozes neurais de alta qualidade (modelo `inworld-tts-1.5-max`) |
| ⏳ **Sistema de Fila** | Processa múltiplas requisições com queue assíncrona |
| 💾 **Cache Inteligente** | Cache de vozes por 5 minutos para reduzir requisições |
| 🛡️ **Anti-Detecção** | Rotação de User-Agent e delays aleatórios |
| 🗑️ **Auto-Limpeza** | Deleta arquivos temporários após 50 segundos |

---

## 📦 Estrutura do Projeto

```
webscrap-tts/
├── telegram_bot.py      # Bot principal do Telegram
├── refresh_token.py     # Script standalone para renovar token
├── webscrap_tts.py      # Scraper CLI interativo (legado)
├── requirements.txt     # Dependências Python
├── Dockerfile           # Container Docker
├── docker-compose.yml   # Orquestração Docker
├── .env                 # Variáveis de ambiente (não commitado)
├── .env.example         # Exemplo de configuração
└── output/              # Áudios gerados (temporário)
```

---

## ⚙️ Instalação

### Requisitos
- Python 3.10+
- Conta no Telegram (@BotFather)
- Conta na Inworld AI (https://platform.inworld.ai)

### 1. Clone o repositório

```bash
git clone https://github.com/sonyddr666/webscrap-tts.git
cd webscrap-tts
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure o `.env`

```bash
cp .env.example .env
```

Edite o `.env`:

```env
# Telegram
TELEGRAM_BOT_TOKEN=seu_token_do_botfather

# Inworld (inicial - será renovado automaticamente)
INWORLD_TOKEN=eyJraWQi...
WORKSPACE_ID=default--pb4bm1oowkem_r9ri2wiw

# Firebase (para renovação automática)
FIREBASE_REFRESH_TOKEN=AMf-vBwy...

# Voz padrão
TTS_VOICE_ID=default--pb4bm1oowkem_r9ri2wiw__sony
```

### 4. Execute

```bash
python telegram_bot.py
```

---

## 🔑 Sistema de Autenticação

O bot usa um sistema de autenticação em camadas que simula o comportamento do browser:

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUXO DE AUTENTICAÇÃO                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. FIREBASE_REFRESH_TOKEN (longa duração)                      │
│              │                                                  │
│              ▼                                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │ securetoken.googleapis.com/v1/token      │                  │
│  │ → Retorna: id_token (Firebase JWT)       │                  │
│  └──────────────────────────────────────────┘                  │
│              │                                                  │
│              ▼                                                  │
│  2. Firebase JWT (~1 hora)                                      │
│              │                                                  │
│              ▼                                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │ platform.inworld.ai/.../token:generate   │                  │
│  │ → Retorna: TTS Token com scope we:tts    │                  │
│  └──────────────────────────────────────────┘                  │
│              │                                                  │
│              ▼                                                  │
│  3. TTS Token (JWT com we:tts scope) ~1 hora                   │
│              │                                                  │
│              ▼                                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │ api.inworld.ai/tts/v1/voice              │                  │
│  │ → Retorna: audioContent (Base64 MP3)     │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Obtendo o FIREBASE_REFRESH_TOKEN

1. Acesse https://platform.inworld.ai
2. Faça login com sua conta Google
3. Abra DevTools (F12) → **Application** → **Cookies**
4. Procure o cookie `IW-PROD-TOKEN`
5. Copie o valor do campo `refreshToken` dentro do JSON

---

## 📱 Comandos do Bot

| Comando | Descrição |
|:--------|:----------|
| `/start` | Mostra menu inicial e voz atual |
| `/voices` | Lista as 15 primeiras vozes disponíveis |
| `/voice` | Menu interativo para trocar de voz |
| `/idioma` | Filtra vozes por idioma (13 idiomas) |
| `/token` | Renova o token TTS manualmente |
| `[qualquer texto]` | Gera áudio com a voz selecionada |

---

## 🌍 Idiomas Suportados

| Código | Idioma | Vozes |
|:-------|:-------|:------|
| `pt` | 🇧🇷 Português | sony, Heitor, Maitê |
| `en` | 🇺🇸 English | Blake, Luna, Alex, Ashley, Craig, +16 |
| `es` | 🇪🇸 Español | Diego, Lupita, Miguel, Rafael |
| `fr` | 🇫🇷 Français | Alain, Étienne, Hélène, Mathieu |
| `de` | 🇩🇪 Deutsch | Johanna, Josef |
| `ja` | 🇯🇵 日本語 | Asuka, Satoshi |
| `ko` | 🇰🇷 한국어 | Hyunwoo, Minji, Seojun, Yoona |
| `zh` | 🇨🇳 中文 | Jing, Xiaoyin, Xinyi, Yichen |
| `ru` | 🇷🇺 Русский | Dmitry, Elena, Nikolai, Svetlana |
| `nl` | 🇳🇱 Nederlands | Erik, Katrien, Lennart, Lore |
| `it` | 🇮🇹 Italiano | Gianni, Orietta |
| `ar` | 🇸🇦 العربية | Nour, Omar |
| `he` | 🇮🇱 עברית | Oren, Yael |
| `hi` | 🇮🇳 हिन्दी | Manoj, Riya |
| `pl` | 🇵🇱 Polski | Szymon, Wojciech |

---

## 🧠 Detalhes Técnicos

### Payload da API TTS

```json
{
  "text": "Seu texto aqui",
  "voice_id": "default--pb4bm1oowkem_r9ri2wiw__sony",
  "model_id": "inworld-tts-1.5-max",
  "audio_config": {
    "audio_encoding": "MP3",
    "speaking_rate": 1.0,
    "sample_rate_hertz": 48000
  },
  "temperature": 1.0
}
```

### Endpoints da API (Engenharia Reversa)

| Endpoint | Método | Descrição |
|:---------|:-------|:----------|
| `api.inworld.ai/voices/v1/workspaces/{id}/voices` | GET | Lista vozes disponíveis |
| `api.inworld.ai/tts/v1/voice` | POST | Gera áudio TTS |
| `platform.inworld.ai/.../token:generate` | POST | Gera token com scope TTS |
| `securetoken.googleapis.com/v1/token` | POST | Renova Firebase token |

### Estrutura do Token JWT TTS

```json
{
  "aud": "world-engine",
  "scope": "we:session we:utils we:tts we:workspace:...",
  "ws": "default--pb4bm1oowkem_r9ri2wiw",
  "app_t": "STUDIO",
  "exp": 1770169557
}
```

> ⚠️ **Importante**: O token TTS expira em ~1 hora. Use `/token` para renovar.

---

## 🐳 Docker

### Build e Run

```bash
docker-compose up --build -d
```

### Ver logs

```bash
docker-compose logs -f
```

### Parar

```bash
docker-compose down
```

---

## 🔧 Solução de Problemas

| Erro | Causa | Solução |
|:-----|:------|:--------|
| **401 Unauthorized** | Token expirado | Use `/token` para renovar |
| **500 "billing account"** | Token sem scope TTS | Verifique FIREBASE_REFRESH_TOKEN |
| **429 Too Many Requests** | Rate limit | Aguarde alguns minutos |
| **403 Forbidden** | IP bloqueado | Use VPN ou aguarde |
| **Arquivo 0KB** | Falha na decodificação | Verifique os logs |

---

## 📊 Arquitetura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Telegram      │────▶│  telegram_bot   │────▶│   Inworld AI    │
│   Usuário       │◀────│     .py         │◀────│      API        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Audio Queue    │
                        │   (asyncio)     │
                        └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │   output/       │
                        │  .mp3 files     │
                        └─────────────────┘
```

---

## 🔄 Script de Renovação Standalone

O `refresh_token.py` pode ser usado separadamente para gerar tokens:

```bash
python refresh_token.py
```

Resultado:
```
==================================================
🔑 Inworld TTS Token Generator
==================================================
🔄 Renovando token Firebase...
✅ Firebase token renovado!
🔄 Gerando token TTS...
✅ Token TTS gerado!
📅 Expira em: 2026-02-04T02:45:19Z
==================================================
✅ Token salvo em token.txt!
==================================================
```

---

## ⚠️ Aviso Legal

Este projeto é para **fins educacionais**. Use com responsabilidade:

- ✅ Respeite rate limits
- ✅ Não compartilhe tokens publicamente
- ⚠️ A API pode mudar sem aviso prévio
- ⚠️ Pode violar Termos de Serviço da Inworld

---

## 📝 Changelog

### v3.0 (2026-02-03)
- ✅ Corrigido endpoint de renovação de token
- ✅ Adicionado comando `/token` para renovação manual
- ✅ Sistema de autenticação via Firebase refresh token
- ✅ Modo DEBUG para troubleshooting

### v2.0
- ✅ Bot Telegram com comandos interativos
- ✅ Sistema de fila (queue) para processamento
- ✅ Filtro por idioma
- ✅ Seleção de voz por usuário

### v1.0
- ✅ Scraper CLI básico
- ✅ Listagem de vozes
- ✅ Geração de áudio

---

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/melhoria`)
3. Commit suas mudanças (`git commit -m 'Add: nova feature'`)
4. Push para a branch (`git push origin feature/melhoria`)
5. Abra um Pull Request

---

## 📄 Licença

MIT License - Use como quiser, mas por sua conta e risco.

---

**Desenvolvido com ☕ e 🎧**