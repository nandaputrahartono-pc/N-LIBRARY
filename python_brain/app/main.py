import os
import json
import time
import requests
from collections import defaultdict
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
import tempfile
import edge_tts
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

# Model yang dipakai
MODEL = "openai/gpt-oss-120b"

app = FastAPI(
    title="N-LIBRARY Brain",
    description="AI Brain microservice untuk N-LIBRARY Discord Bot",
    version="0.2.0",
)


# ============================================================
# Conversation Memory (In-Memory, Per-User)
# ============================================================

MAX_MEMORY_PER_USER = 30  # Simpan 30 interaksi terakhir per user

# Format: { "user_id": [ {"role": "user"/"assistant", "content": "...", "channel": "...", "ts": 123} ] }
conversation_memory: Dict[str, list] = defaultdict(list)


def get_user_memory(user_id: str) -> list:
    """Ambil riwayat percakapan user, potong kalau kelewat panjang."""
    return conversation_memory[user_id][-MAX_MEMORY_PER_USER:]


def add_to_memory(user_id: str, role: str, content: str, channel: str):
    """Tambahkan pesan ke ingatan user."""
    conversation_memory[user_id].append({
        "role": role,
        "content": content,
        "channel": channel,
        "ts": time.time(),
    })
    # Trim kalau kepanjangan
    if len(conversation_memory[user_id]) > MAX_MEMORY_PER_USER * 2:
        conversation_memory[user_id] = conversation_memory[user_id][-MAX_MEMORY_PER_USER:]


def build_memory_context(user_id: str, current_channel: str) -> str:
    """Format ingatan user jadi teks konteks buat system prompt."""
    memory = get_user_memory(user_id)
    if not memory:
        return ""
    
    lines = ["\n--- INGATAN PERCAKAPAN KAMU DENGAN USER INI ---"]
    for entry in memory:
        prefix = "User" if entry["role"] == "user" else "Kamu"
        ch = entry.get("channel", "?")
        if ch != current_channel:
            lines.append(f"[di #{ch}] {prefix}: {entry['content']}")
        else:
            lines.append(f"{prefix}: {entry['content']}")
    lines.append("--- (akhir ingatan) ---")
    return "\n".join(lines)


# ============================================================
# Request / Response Models
# ============================================================

class ServerMember(BaseModel):
    name: str
    id: str
    status: str

class ServerState(BaseModel):
    guild_id: str
    server_name: str
    is_admin: bool
    text_channels: List[str] = []
    voice_channels: List[str] = []
    activities: Dict[str, str] = {}
    recent_history: List[str] = []
    members: List[ServerMember] = []

class ChatRequest(BaseModel):
    """Request dari Rust Gateway."""
    message: str
    user_id: str = ""
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
        "Kamu adalah N-LIBRARY, teman ngobrol di server Discord.\n"
        "Kepribadian:\n"
        "- Ngobrol santai, natural, kayak temen biasa. Pakai bahasa Indonesia sehari-hari.\n"
        "- JANGAN terlalu formal atau kaku. Tapi juga jangan lebay.\n"
        "- Pakai emoji SECUKUPNYA, kayak manusia biasa. Maksimal 1-2 emoji per pesan, dan hanya yang umum (😂🤣😊😁👍🔥💀). Jangan spam emoji.\n"
        "- JANGAN menawarkan bantuan soal server/role/channel kecuali user MEMANG nanya atau minta. "
        "Kalau lagi ngobrol santai, ya ikut ngobrol santai aja. Jangan nyerocos soal fitur.\n"
        "- Pahami konteks percakapan. Kalau user lagi curhat, dengerin. Kalau lagi bercanda, ikut bercanda. "
        "Jangan banting stir ke topik server management.\n"
        "- Jawab singkat dan to the point kalau pertanyaannya simpel. Gak perlu panjang lebar.\n"
        f"\nKamu sedang ngobrol dengan {request.user_name} di channel #{request.channel_name}.\n"
    )

    # Ingatan lintas channel
    if request.user_id:
        memory_ctx = build_memory_context(request.user_id, request.channel_name)
        if memory_ctx:
            prompt += memory_ctx + "\n"

    if request.server_state:
        state = request.server_state

        # Info konteks server — AI punya tapi jangan dipamerkan kecuali diminta
        prompt += (
            f"\n--- KONTEKS SERVER (pakai info ini HANYA kalau relevan dengan pertanyaan user) ---\n"
            f"Server: {state.server_name}\n"
            f"Status {request.user_name}: {'Admin' if state.is_admin else 'Member biasa'}\n"
        )
        
        prompt += f"Channel Text: {', '.join(state.text_channels)}\n"
        prompt += "Voice Channels:\n"
        for vc in state.voice_channels:
            prompt += f"- {vc}\n"

        if state.activities:
            activities_str = ", ".join(f"{user} lagi {act}" for user, act in state.activities.items())
            prompt += f"Aktivitas Member: {activities_str}\n"

        if state.recent_history:
            prompt += "\n--- 10 Chat Terakhir di Channel Ini ---\n"
            for msg in state.recent_history:
                prompt += f"{msg}\n"
            prompt += "------------------------\n"
            
        prompt += "\n--- DAFTAR MEMBER SERVER (Nama, Status, ID) ---\n"
        for m in state.members:
            prompt += f"- {m.name} ({m.status}) [ID: {m.id}]\n"

        prompt += (
            "\n--- ATURAN PENTING TENTANG MENTION/TAG USER ---\n"
            "- Kalau user minta kamu nge-tag atau manggil seseorang, JANGAN pakai '@nama' biasa.\n"
            "- Kamu HARUS pakai format <@ID_USER> supaya orangnya beneran ke-tag. (Contoh: <@1234567890>)\n"
            "- Kamu bisa cari ID mereka di DAFTAR MEMBER SERVER di atas. Walaupun user nulis nama singkatannya doang (contoh 'hoshikage'), cari nama panjangnya (contoh 'hoshikage*30') dan ambil ID-nya.\n"
            "- PENTING: Saat nge-tag, gabungkan ke dalam obrolan santai yang natural! BUKAN gaya robot/command. \n"
            "  (CONTOH BENAR: 'Woi <@1234567890>, dicariin tuh suruh temenin voice! 😂')\n"
            "  (CONTOH SALAH: 'Berikut tagnya: <@1234567890>')\n"
        )
            
        prompt += (
            "\n--- ATURAN TOOL (internal, jangan disebutkan ke user kecuali relevan) ---\n"
            "- Kamu punya fungsi `manage_role` untuk tambah/hapus role (hanya Admin).\n"
            "- Kamu punya fungsi `manage_voice` untuk masuk (join) atau keluar (leave) Voice Channel.\n"
            "- JANGAN pernah menawarkan fitur manage_role duluan. Tunggu user yang minta.\n"
            "- Kalau disuruh 'masuk voice', panggil `manage_voice` dengan action 'join'.\n"
            "- Kalau disuruh 'keluar voice', panggil `manage_voice` dengan action 'leave'.\n"
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
    },
    {
        "type": "function",
        "function": {
            "name": "manage_voice",
            "description": "Menyuruh bot untuk masuk (join) atau keluar (leave) dari Voice Channel user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["join", "leave"],
                        "description": "Tindakan: 'join' untuk menyuruh bot masuk ke VC user, 'leave' untuk keluar.",
                    },
                },
                "required": ["action"],
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

def execute_manage_voice(guild_id: str, user_id: str, action: str) -> str:
    """Eksekusi memanggil internal API Rust untuk join/leave voice."""
    try:
        response = requests.post(
            "http://localhost:8080/api/voice_control",
            json={
                "guild_id": guild_id,
                "user_id": user_id,
                "action": action
            },
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                if action == "join":
                    return "Berhasil masuk ke Voice Channel! Silakan sapa user di VC."
                else:
                    return "Berhasil keluar dari Voice Channel."
            else:
                return f"Gagal {action} Voice Channel: {result.get('error')}"
        else:
            return f"Gagal memanggil API Voice: HTTP {response.status_code}"
    except Exception as e:
        return f"Error menghubungi server Rust untuk Voice: {e}"


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
    Endpoint utama — terima pesan dari Rust Gateway, proses via Groq,
    termasuk eksekusi Tool Calling jika diperlukan.
    """
    if not groq_client:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY belum dikonfigurasi. Isi dulu di file .env!",
        )

    # Simpan pesan user ke ingatan
    if request.user_id:
        add_to_memory(request.user_id, "user", request.message, request.channel_name)

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
                elif function_name == "manage_voice":
                    if not request.server_state:
                        tool_result = "Gagal: Tidak ada context server."
                    else:
                        tool_result = execute_manage_voice(
                            guild_id=request.server_state.guild_id,
                            user_id=request.user_id,
                            action=function_args.get("action")
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

        # Simpan balasan AI ke ingatan
        if request.user_id:
            add_to_memory(request.user_id, "assistant", reply, request.channel_name)

        return ChatResponse(reply=reply)

    except Exception as e:
        print(f"[ERROR] Groq API error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memproses AI: {str(e)}",
        )

@app.post("/api/voice_chat")
async def voice_chat(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    user_name: str = Form(...),
    channel_name: str = Form(...),
    participant_count: int = Form(...),
    server_state_json: str = Form(None)
):
    """
    Menerima rekaman suara dari Rust, mengubah ke teks (STT),
    memproses jawaban LLM, dan mengembalikan file MP3 (TTS).
    """
    if not groq_client:
        raise HTTPException(status_code=503, detail="Groq API Key missing")

    # 1. Simpan audio sementara
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
        content = await file.read()
        tmp_wav.write(content)
        wav_path = tmp_wav.name

    try:
        # 2. STT via Groq Whisper
        with open(wav_path, "rb") as f:
            transcript_res = groq_client.audio.transcriptions.create(
                file=("audio.wav", f),
                model="whisper-large-v3",
                prompt="Teks dalam bahasa Indonesia",
                language="id"
            )
        
        user_text = transcript_res.text.strip()
        
        # 3. Filter Halusinasi Silence dari Whisper
        import re
        lower_text = user_text.lower()
        clean_text = re.sub(r'[^\w\s]', '', lower_text).strip()
        
        ignore_phrases = [
            "terima kasih telah menonton", 
            "terima kasih",
            "halo",
            "terima kasih sudah menonton",
            "terima kasih banyak"
        ]
        
        from fastapi import Response
        if not clean_text or clean_text in ignore_phrases or len(clean_text) < 2:
            print(f"[Voice] Ignored (Silence/Hallucination): {user_text}")
            return Response(status_code=204)

        print(f"[Voice] {user_name} berkata: {user_text}")

        # 4. Dynamic Wake Word
        if participant_count > 2:
            wake_words = ["ai", "bot", "n-library", "n library", "gadis"]
            if not any(word in clean_text for word in wake_words):
                print(f"[Voice] Ignored (No wake word & rame): {user_text}")
                return Response(status_code=204)

        # 5. LLM Chat (Rekonstruksi request)
        server_state = None
        if server_state_json:
            try:
                server_state_dict = json.loads(server_state_json)
                server_state = ServerState(**server_state_dict)
            except Exception:
                pass

        chat_req = ChatRequest(
            message=user_text,
            user_id=user_id,
            user_name=user_name,
            channel_name=channel_name,
            server_state=server_state
        )

        # Process as normal chat (tapi bisa panggil tool)
        response_model = await chat(chat_req)
        ai_reply = response_model.reply
        
        print(f"[AI Voice Reply] {ai_reply}")

        # 6. TTS via Edge-TTS (Strip emojis first!)
        import re
        # Hapus emoji / simbol aneh agar TTS gak bacain kode emot (tapi tetap pertahankan huruf, angka, tanda baca dasar)
        tts_text = re.sub(r'[^\w\s,.?!;:\'"-]', '', ai_reply)
        
        voice = "id-ID-GadisNeural"
        tts = edge_tts.Communicate(tts_text, voice)
        
        mp3_path = wav_path.replace(".wav", ".mp3")
        await tts.save(mp3_path)

        return FileResponse(mp3_path, media_type="audio/mpeg", filename="reply.mp3")

    except Exception as e:
        print(f"[ERROR] Voice Pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
# ============================================================
# Startup
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Log saat server mulai."""
    print("🐍 N-LIBRARY Brain (Python) sudah online!")
    print(f"   Model: {MODEL}")
    print(f"   Groq API: {'✅ Configured' if GROQ_API_KEY else '❌ NOT configured'}")
