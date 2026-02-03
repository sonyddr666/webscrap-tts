# 🎙️ Inworld AI TTS Scraper - Automação Profissional

Ferramenta de engenharia reversa para geração de áudio neural usando a API interna da Inworld AI.

---

## ✨ Funcionalidades do v2

| Feature | Descrição |
|:--------|:----------|
| 🔄 **Auto-Validação JWT** | Decodifica o token e avisa quando está para expirar |
| 💾 **Cache de Token** | Salva automaticamente em `data/token_cache.json` |
| 🔁 **Retry com Backoff** | Tenta novamente com delay exponencial em caso de erro |
| 🕵️ **Anti-Detecção** | Rotação de User-Agent e delays aleatórios |
| 🌐 **Filtro por Idioma** | Menu interativo com 15 idiomas suportados |
| 🎤 **Seletor de Voz** | Escolha entre 66+ vozes disponíveis |
| 📁 **Nomes Automáticos** | Arquivos salvos com timestamp e texto |
| 📊 **Estatísticas** | Monitora requisições, erros, e bytes transferidos |
| 📝 **Logging Completo** | Salva tudo em `data/inworld_scraper.log` |

---

## 📦 Estrutura do Projeto

```
ttts aleatorio/
├── inworld_scraper.py       # v1 simples
├── inworld_scraper_v2.py    # v2 profissional ⭐
├── README.md
├── data/                    # Criado automaticamente
│   ├── token_cache.json
│   └── inworld_scraper.log
└── output/                  # Áudios gerados
    └── audio_YYYYMMDD_HHMMSS_texto.mp3
```

---

## 🚀 Instalação

```bash
pip install requests
```

---

## ⚙️ Configuração do Token

O token JWT é extraído do navegador e tem **validade limitada** (~1 hora).

### Como Atualizar

1. Abra [Inworld Studio](https://studio.inworld.ai/)
2. DevTools (F12) → **Network**
3. Filtre por `voice` ou `voices`
4. Copie o header `Authorization: Bearer eyJ...`
5. Cole na variável `TOKEN` do script **ou** execute:

```python
from inworld_scraper_v2 import salvar_token_cache
salvar_token_cache("seu_novo_token_aqui")
```

---

## 🎮 Uso

```bash
python inworld_scraper_v2.py
```

### Fluxo Interativo

```text
╔══════════════════════════════════════════════════════════════╗
║   🎙️  INWORLD AI TTS SCRAPER v2.0                           ║
╚══════════════════════════════════════════════════════════════╝

✅ Token válido por 0d 1h

╔════════════════════════════════════════╗
║       ESCOLHA O IDIOMA DAS VOZES       ║
╚════════════════════════════════════════╝

 1. 🇧🇷 Português       2. 🇺🇸 English         3. 🇪🇸 Español
 ...

📍 Digite o número: 1
✅ Selecionado: 🇧🇷 Português

Encontradas 66 vozes em 🇧🇷 Português

======================================================================
#    Nome                 Idiomas         Tags
======================================================================
1    sony                                 cartoonish, clear, bright
2    Alex                                 friendly, expressive
...

📍 Escolha o número da voz (1-15, Enter=1): 2

🎤 Voz selecionada: Alex

────────────────────────────────────────────────────────────
💬 Digite textos para gerar áudio
   Comandos: 'sair', 'stats', 'voz'
────────────────────────────────────────────────────────────

📝 Texto: Olá, este é um teste de voz neural
🎙️ Gerando áudio: 'Olá, este é um teste de voz neural'...
✅ Áudio salvo: output\audio_20260203_221500_Ola_este_e_um_teste.mp3
```

### Comandos Disponíveis

| Comando | Ação |
|:--------|:-----|
| `sair` | Encerra e mostra estatísticas |
| `stats` | Exibe estatísticas da sessão |
| `voz` | Abre menu para trocar de voz |

---

## 🧠 Detalhes Técnicos

### Payload da API TTS

```json
{
  "text": "Seu texto aqui",
  "voice_id": "default--pb4bm1oowkem_r9ri2wiw__Alex",
  "model_id": "inworld-tts-1.5-max",
  "audio_config": {
    "audio_encoding": "MP3",
    "speaking_rate": 1.0,
    "sample_rate_hertz": 48000
  },
  "temperature": 1.0
}
```

### Endpoints Descobertos (Engenharia Reversa)

| Endpoint | Método | Descrição |
|:---------|:-------|:----------|
| `/voices/v1/workspaces/{id}/voices` | GET | Lista vozes |
| `/tts/v1/voice` | POST | Gera áudio |

### Resposta da API

A API retorna JSON com `audioContent` em **Base64**:

```json
{
  "audioContent": "/+NIxAAAAAANIAAAAAED..."
}
```

O script decodifica automaticamente para bytes MP3.

---

## 🔧 Solução de Problemas

| Erro | Causa | Solução |
|:-----|:------|:--------|
| **401 Unauthorized** | Token expirado | Atualize o token (veja acima) |
| **429 Too Many Requests** | Rate limit | O script aguarda 30s e tenta novamente |
| **403 Forbidden** | Detecção de bot | Aguarde alguns minutos |
| **Arquivo 0KB** | Falha na decodificação | Verifique os logs em `data/` |

---

## ⚠️ Aviso Legal

Este projeto é para **fins educacionais**. Use com responsabilidade:

- ✅ Respeite rate limits
- ✅ Não compartilhe seu token publicamente
- ⚠️ A API pode mudar sem aviso prévio
- ⚠️ Pode violar os Termos de Serviço da Inworld

---

## 📊 Idiomas Suportados

| Código | Idioma |
|:-------|:-------|
| `pt` | Português 🇧🇷 |
| `en` | English 🇺🇸 |
| `es` | Español 🇪🇸 |
| `fr` | Français 🇫🇷 |
| `de` | Deutsch 🇩🇪 |
| `it` | Italiano 🇮🇹 |
| `nl` | Nederlands 🇳🇱 |
| `pl` | Polski 🇵🇱 |
| `ru` | Русский 🇷🇺 |
| `zh` | 中文 🇨🇳 |
| `ja` | 日本語 🇯🇵 |
| `ko` | 한국어 🇰🇷 |
| `hi` | हिन्दी 🇮🇳 |
| `ar` | العربية 🇸🇦 |
| `he` | עברית 🇮🇱 |