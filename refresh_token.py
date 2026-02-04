#!/usr/bin/env python3
"""
Script para renovar o INWORLD_TOKEN usando o refreshToken do Firebase
Endpoint correto: /ai/inworld/portal/v1alpha/workspaces/{workspace_id}/token:generate
"""

import os
import requests
import json
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configurações do .env (SEM CHAVES HARDCODED!)
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyAPVBLVid0xPwjuU4Gmn_6_GyqxBq-SwQs")
FIREBASE_REFRESH_TOKEN = os.getenv("FIREBASE_REFRESH_TOKEN")
WORKSPACE_ID = os.getenv("WORKSPACE_ID", "default--pb4bm1oowkem_r9ri2wiw")


def refresh_firebase_token():
    """Renova o accessToken usando o refreshToken do Firebase"""
    if not FIREBASE_REFRESH_TOKEN:
        print("❌ FIREBASE_REFRESH_TOKEN não encontrado no .env!")
        return None
    
    print("🔄 Renovando token Firebase...")
    
    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    payload = {"grant_type": "refresh_token", "refresh_token": FIREBASE_REFRESH_TOKEN}
    
    response = requests.post(url, data=payload)
    
    if response.status_code == 200:
        data = response.json()
        access_token = data.get("id_token")
        print(f"✅ Firebase token renovado!")
        return access_token
    else:
        print(f"❌ Erro ao renovar Firebase token: {response.status_code}")
        print(response.text)
        return None


def generate_tts_token(firebase_token):
    """Gera o token TTS usando o endpoint correto do portal"""
    print("🔄 Gerando token TTS...")
    
    # Endpoint correto que gera token com scope we:tts
    url = f"https://platform.inworld.ai/ai/inworld/portal/v1alpha/workspaces/{WORKSPACE_ID}/token:generate"
    
    headers = {
        "authorization": f"Bearer {firebase_token}",
        "content-type": "text/plain;charset=UTF-8",
        "grpc-metadata-x-authorization-bearer-type": "firebase",
        "origin": "https://platform.inworld.ai",
        "referer": f"https://platform.inworld.ai/v2/workspaces/{WORKSPACE_ID}/tts-playground",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = json.dumps({})
    
    response = requests.post(url, headers=headers, data=payload, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        tts_token = data.get("token")
        expiration = data.get("expirationTime")
        session_id = data.get("sessionId")
        print(f"✅ Token TTS gerado!")
        print(f"📅 Expira em: {expiration}")
        print(f"🆔 Session: {session_id}")
        return tts_token
    else:
        print(f"❌ Erro ao gerar token TTS: {response.status_code}")
        print(response.text)
        return None


def main():
    print("=" * 50)
    print("🔑 Inworld TTS Token Generator")
    print("=" * 50)
    
    # Passo 1: Renovar token Firebase
    firebase_token = refresh_firebase_token()
    if not firebase_token:
        return
    
    # Passo 2: Gerar token TTS (com scope we:tts)
    tts_token = generate_tts_token(firebase_token)
    if not tts_token:
        return
    
    # Passo 3: Salvar em token.txt
    with open("token.txt", "w") as f:
        f.write(tts_token)
    
    print("=" * 50)
    print(f"✅ Token salvo em token.txt!")
    print(f"📋 Token: {tts_token[:80]}...")
    print("=" * 50)


if __name__ == "__main__":
    main()
