"""
N-LIBRARY — Python Brain (The Brain)
FastAPI microservice untuk AI chatbot menggunakan Groq + Llama 3.3 70B.
"""

import os
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from groq import Groq
from dotenv import load_dotenv
from pathlib import Path

# Load .env dari root project (dua level di atas: python_brain/app/ -> python_brain/ -> root)
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("⚠️  WARNING: GROQ_API_KEY belum diisi di file .env!")
    print("   AI chatbot tidak akan bisa berfungsi sampai API key diisi.")

# Inisialisasi Groq client
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Model yang dipakai (Update: menggunakan model OSS terbaru dari Groq)
MODEL = "openai/gpt-oss-120b"

app = FastAPI(
    title="N-LIBRARY Brain",
    description="AI Brain microservice untuk N-LIBRARY Discord Bot",
    version="0.1.0",
)


# ============================================================
# Request / Response Models
# ============================================================

class ServerState(BaseModel):
    guild_id: str
    server_name: str
    is_admin: bool
    text_channels: List[str] = []
    voice_channels: List[str] = []
    activities: Dict[str, str] = {}
    recent_history: List[str] = []

class ChatRequest(BaseModel):
    """Request dari Rust Gateway."""
    message: str
    user_name: str = "User"
    channel_name: str = "general"
    server_state: Optional[ServerState] = None


class ChatResponse(BaseModel):
    """Response balik ke Rust Gateway."""
    reply: str


# ============================================================
# System Prompt
# ============================================================

def build_system_prompt(request: ChatRequest) -> str:
    """Bikin system prompt dinamis yang santai + sadar konteks."""
    prompt = (
        "Kamu adalah N-LIBRARY, AI asisten server Discord.\n"
        "Cara ngobrolmu santai, asik, pakai bahasa Indonesia sehari-hari.\n"
        f"Kamu sedang ngobrol dengan {request.user_name} di channel #{request.channel_name}.\n"
    )

    if request.server_state:
        state = request.server_state
        prompt += f"\n--- INFO SERVER: {state.server_name} ---\n"
        prompt += f"Status {request.user_name}: {'Admin/Bos Server 👑' if state.is_admin else 'Member biasa'}\n"
        
        prompt += f"\nChannel Text: {', '.join(state.text_channels)}\n"
        prompt += "Voice Channels (dan siapa saja di dalamnya):\n"
        for vc in state.voice_channels:
            prompt += f"- {vc}\n"

        if state.activities:
            activities_str = ", ".join(f"{user} lagi {act}" for user, act in state.activities.items())
            prompt += f"\nAktivitas Member: {activities_str}\n"

        if state.recent_history:
            prompt += "\n--- 10 Chat Terakhir (Ingatan Jangka Pendek) ---\n"
            for msg in state.recent_history:
                prompt += f"{msg}\n"
            prompt += "----------------------------------------------\n"
            
        prompt += (
            "\nAturan Tool/Fungsi:\n"
            "- Kamu bisa mengelola role user dengan fungsi `manage_role` (action: 'add' atau 'remove').\n"
            "- HANYA izinkan penambahan/penghapusan role JIKA user yang meminta adalah Admin (Status: Admin/Bos Server 👑).\n"
            "- Jika user BUKAN Admin meminta kelola role, tolak dengan santai (misal: 'Yee lu bukan admin bro, minta izin dulu gih').\n"
            "- Jika diminta mengganti role (misal: ganti Member jadi VIP), jalankan tool ini 2 kali: 1 untuk hapus role lama, 1 untuk tambah role baru.\n"
        )
        
    return prompt


# ============================================================
# Tools
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "manage_role",
            "description": "Menambahkan atau menghapus role user di server Discord. Hanya jalankan jika yang meminta adalah Admin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove"],
                        "description": "Tindakan: 'add' untuk menambah, 'remove' untuk menghapus role.",
                    },
                    "user_name": {
                        "type": "string",
                        "description": "Nama user di Discord yang akan dikelola rolenya",
                    },
                    "role_name": {
                        "type": "string",
                        "description": "Nama role (contoh: VIP, Member)",
                    }
                },
                "required": ["action", "user_name", "role_name"],
            },
        },
    }
]

def execute_manage_role(guild_id: str, action: str, user_name: str, role_name: str) -> str:
    """Eksekusi memanggil internal API Rust untuk kelola role."""
    try:
        response = requests.post(
            "http://localhost:8080/api/role",
            json={
                "guild_id": guild_id,
                "action": action,
                "user_name": user_name,
                "role_name": role_name
            },
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                action_str = "menambahkan" if action == "add" else "menghapus"
                return f"Berhasil {action_str} role {role_name} untuk {user_name}!"
            else:
                return f"Gagal kelola role: {result.get('error')}"
        else:
            return f"Gagal memanggil API: HTTP {response.status_code}"
    except Exception as e:
        return f"Error menghubungi server Rust: {e}"


# ============================================================
# Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Health check — buat ngecek server nyala atau engga."""
    return {
        "status": "ok",
        "brain": "online",
        "model": MODEL,
        "groq_configured": GROQ_API_KEY is not None,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint utama — terima pesan dari Rust Gateway, proses via Groq Llama,
    termasuk eksekusi Tool Calling jika diperlukan.
    """
    if not groq_client:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY belum dikonfigurasi. Isi dulu di file .env!",
        )

    system_prompt = build_system_prompt(request)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.message},
    ]

    try:
        # Step 1: Panggil Groq dengan tools
        completion = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1024,
        )

        response_message = completion.choices[0].message
        tool_calls = response_message.tool_calls

        # Step 2: Cek apakah AI memutuskan untuk memanggil tool
        if tool_calls:
            # Masukkan balasan AI (yang berisi tool call) ke riwayat pesan
            messages.append(response_message)
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                tool_result = "Fungsi tidak ditemukan."
                
                if function_name == "manage_role":
                    # Cek keamanan di sisi Python (meskipun AI sudah diinstruksikan)
                    if not request.server_state or not request.server_state.is_admin:
                        tool_result = "Tolak! User bukan Admin. Bilang ke user kalau dia gak punya akses."
                    else:
                        guild_id = request.server_state.guild_id
                        tool_result = execute_manage_role(
                            guild_id=guild_id,
                            action=function_args.get("action"),
                            user_name=function_args.get("user_name"),
                            role_name=function_args.get("role_name")
                        )
                
                # Masukkan hasil tool execution ke riwayat pesan
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": tool_result,
                })
            
            # Step 3: Panggil Groq lagi dengan hasil tool execution
            second_completion = groq_client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.7,
            )
            reply = second_completion.choices[0].message.content
        else:
            reply = response_message.content

        if not reply:
            reply = "Hmm, aku gak tau harus jawab apa 😅"

        return ChatResponse(reply=reply)

    except Exception as e:
        print(f"[ERROR] Groq API error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memproses AI: {str(e)}",
        )


# ============================================================
# Startup
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Log saat server mulai."""
    print("🐍 N-LIBRARY Brain (Python) sudah online!")
    print(f"   Model: {MODEL}")
    print(f"   Groq API: {'✅ Configured' if GROQ_API_KEY else '❌ NOT configured'}")
