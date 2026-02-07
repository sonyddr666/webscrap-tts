# Billing Info - Consulta de Uso Inworld AI
# =============================================
# Comando /uso - mostra todos os dados de billing

import os
import json
import requests
from urllib.parse import unquote
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

load_dotenv()

# Configurações
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyAPVBLVid0xPwjuU4Gmn_6_GyqxBq-SwQs")
WORKSPACE_ID = os.getenv("WORKSPACE_ID", "default--pb4bm1oowkem_r9ri2wiw")
BILLING_ACCOUNT_ID = os.getenv("BILLING_ACCOUNT_ID", "af231990-0044-4742-ac81-bb435a5379ab")

# Arquivo de cookies
COOKIES_FILE = Path(__file__).parent / "inworld_cookies.json"

# Cache
_auth_token = None


def load_cookies() -> dict:
    if COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_cookies(cookies: dict):
    with open(COOKIES_FILE, 'w') as f:
        json.dump(cookies, f, indent=2)


def refresh_firebase_token(refresh_token: str) -> dict:
    """Renova token Firebase"""
    try:
        url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
        payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        response = requests.post(url, data=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return {
                "id_token": data.get("id_token"),
                "refresh_token": data.get("refresh_token")
            }
    except Exception as e:
        print(f"❌ Erro refresh: {e}")
    return None


def get_inworld_auth_token(firebase_token: str) -> str:
    """Gera token Inworld para billing"""
    try:
        url = "https://platform.inworld.ai/v1alpha/users:generateTokenUser"
        headers = {
            "authorization": f"Bearer {firebase_token}",
            "content-type": "text/plain;charset=UTF-8",
            "grpc-metadata-x-authorization-bearer-type": "firebase",
            "origin": "https://platform.inworld.ai",
            "user-agent": "Mozilla/5.0 Chrome/144.0.0.0"
        }
        payload = json.dumps({"token": firebase_token, "type": "AUTH_TYPE_FIREBASE"})
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        if response.status_code == 200:
            return response.json().get("token")
    except Exception as e:
        print(f"❌ Erro token: {e}")
    return None


def get_auth_token() -> str:
    """Obtém token válido"""
    global _auth_token
    
    refresh_token = os.getenv("FIREBASE_REFRESH_TOKEN")
    if not refresh_token:
        cookies = load_cookies()
        refresh_token = cookies.get("_refresh_token")
    
    if refresh_token:
        new_tokens = refresh_firebase_token(refresh_token)
        if new_tokens:
            inworld_token = get_inworld_auth_token(new_tokens["id_token"])
            if inworld_token:
                _auth_token = inworld_token
                return inworld_token
    
    return None


def get_headers(token: str) -> dict:
    return {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "grpc-metadata-x-authorization-bearer-type": "inworld",
        "origin": "https://platform.inworld.ai",
        "user-agent": "Mozilla/5.0 Chrome/144.0.0.0"
    }


def get_quota_report(token: str) -> dict:
    """Obtém quota report"""
    url = f"https://platform.inworld.ai/v1alpha/billing-accounts/{BILLING_ACCOUNT_ID}/quota-report"
    try:
        response = requests.get(url, headers=get_headers(token), timeout=30)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def get_account_config(token: str) -> dict:
    """Obtém config da conta (tier, créditos)"""
    url = f"https://platform.inworld.ai/v1alpha/billing-accounts/{BILLING_ACCOUNT_ID}/account-config"
    try:
        response = requests.get(url, headers=get_headers(token), timeout=30)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def format_usage_report(quota: dict, config: dict) -> str:
    """Formata relatório completo para Telegram"""
    lines = ["📊 **INWORLD TTS - USO**\n"]
    lines.append(f"📅 {datetime.now().strftime('%d/%m %H:%M')}\n")
    
    # Config - Tier e créditos
    if config:
        tier = config.get("tier", "Basic")
        spend = config.get("currentSpend", 0)
        remaining = config.get("freeUsageRemaining", 0)
        
        lines.append(f"🏷️ **Tier:** {tier}")
        lines.append(f"💰 **Gasto:** ${spend:.2f}")
        lines.append(f"🎁 **Crédito:** ${remaining:.2f}\n")
    
    # Quota - Uso por tipo
    if quota:
        quotas = quota.get("quotas", [])
        
        # Agrupa por modelo se tiver
        usage_items = quota.get("usageItems", [])
        
        if usage_items:
            lines.append("📋 **Uso por Modelo:**")
            for item in usage_items:
                model = item.get("model", "unknown")
                chars = item.get("consumed", 0)
                price = item.get("unitPrice", 0)
                
                # Emoji por modelo
                emoji = "🚀" if "max" in model else "⚡" if "mini" in model else "🔊"
                lines.append(f"{emoji} `{model}`")
                lines.append(f"   {chars:,} chars")
        
        # Quotas gerais
        if quotas:
            lines.append("\n📈 **Quotas:**")
            for q in quotas:
                qtype = q.get("quotaType", "")
                used = int(q.get("usedQuota", 0))
                limit = int(q.get("quotaLimit", 0))
                
                if "TTS" in qtype:
                    name = qtype.replace("TTS_", "").replace("_", " ").title()
                    if limit > 0:
                        pct = (used / limit) * 100
                        lines.append(f"• {name}: {used:,}/{limit:,} ({pct:.0f}%)")
                    else:
                        lines.append(f"• {name}: {used:,}")
    
    return "\n".join(lines)


def get_usage_text() -> str:
    """Retorna texto formatado para /uso"""
    token = get_auth_token()
    if not token:
        return "❌ Erro de autenticação. Verifique FIREBASE_REFRESH_TOKEN"
    
    quota = get_quota_report(token)
    config = get_account_config(token)
    
    if not quota and not config:
        return "❌ Não foi possível obter dados de uso"
    
    return format_usage_report(quota, config)


if __name__ == "__main__":
    print("\n" + "="*40)
    print("📊 INWORLD TTS - USO")
    print("="*40)
    print(get_usage_text().replace("**", "").replace("`", ""))
