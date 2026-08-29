# PLAN.md - N-LIBRARY: Refactor ke Autonomous Voice AI Agent (Rust + Python)

> Status: DRAFT v1.0 - Untuk Agent Antigravity
> Author: Nanda Putra (Alata) & Assistant
> Goal: Merombak bot monolit `bot.py` menjadi Distributed System AI Agent yang sadar konteks server.

---

### 1. Visi Proyek

Bukan cuma bot musik / chat. Target akhirnya adalah **AI Agent yang hidup di dalam server Discord**.

Dia harus:
1.  **Tau siapa lu:** Kenal pembuatnya (Alata), tau tujuan bot ini apa.
2.  **Tau keadaan server:** Tau siapa lagi ngobrol, role apa, siapa di VC sama siapa, lagi main game apa (Activity), dan bisa baca history chat.
3.  **Punya ingatan:** Ingat obrolan penting, bisa RAG.
4.  **Bisa bertindak:** Bisa nge-mute orang toxic, play musik kalo disuruh, nambahin role kalo admin yang nyuruh.
5.  **Bisa diajak ngobrol suara:** Masuk VC, dipanggil "halo AI" baru dia jawab, kalo disuruh "mute" dia diem.

### 2. Arsitektur Target: The Body & The Brain

Kita pisah jadi 2 service biar gak bottleneck.

**A. Rust Gateway (The Body) - `rust_gateway/`**
Tugasnya: Cepat, stabil, anti-lag. Ngurus semua koneksi langsung ke Discord.
- Library: `serenity` + `poise` + `songbird` (buat audio)
- Intents WAJIB: `GUILD_PRESENCES`, `GUILD_MEMBERS`, `MESSAGE_CONTENT`, `GUILD_VOICE_STATES`
- Tugas:
  - Denger semua event: message, voice join/leave, presence update.
  - Logging semua chat ke Database.
  - Streaming audio (yt-dlp via songbird).
  - Buka Internal API (localhost:8080) buat disuruh-suruh sama Python.
  - Nangkring di Voice Channel dan capture audio PCM user.

**B. Python Brain (The Brain) - `python_brain/`**
Tugasnya: Mikir. Semua AI ada disini.
- Framework: `FastAPI` (microservice)
- LLM Provider: `GROQ` (Bukan OpenRouter lagi) - Alasan: Super kenceng (500+ tokens/s), free tier unlimited buat Llama 3, latency rendah cocok buat voice agent.
- Model: `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` dari Meta (Open Source, unlimited)
- Library RAG: `LangChain` / `LlamaIndex` + `sentence-transformers` (buat embedding lokal `all-MiniLM-L6-v2` biar gratis, gak perlu call API embedding)
- Vector DB: `ChromaDB` (Rekomendasi buat lu, paling gampang. Gak perlu server, cukup file lokal. Nanti kalo udah besar baru pindah ke Qdrant)
- Tugas:
  - Embedding & RAG.
  - Jadi AI Agent dengan Tool Calling via Groq (support function calling native).
  - Voice Pipeline: STT + LLM (Groq) + TTS.
  - Memory management.

**Alur Komunikasi:**
`User chat di Discord -> Rust Gateway kumpulin context -> POST ke Python Brain /chat -> Python mikir (RAG + Tool) -> Kalo perlu aksi, Python POST balik ke Rust /api/execute -> Rust eksekusi ke Discord -> Python kasih jawaban final`

### 3. Desain RAG & Memory (Jawaban untuk Poin 1)

Lu bilang mau RAG tentang diri lu, tentang bot, tentang server. Dan memory selamanya tapi takut berat.

Solusi: **Tiered Memory**

**Tier 1: Static Knowledge (Tentang Lu & Bot)**
Ini file markdown yang lu tulis manual. Contoh:
- `knowledge/about_creator.md`: "Gua Alata, mahasiswa TI, pembuat bot N-LIBRARY, suka..."
- `knowledge/about_bot.md`: "N-LIBRARY adalah bot untuk..."
- `knowledge/server_rules.md`: Rules server lu.
File ini di-embedding sekali dan jadi pengetahuan dasar AI.

**Tier 2: Hot Memory (30 Hari Terakhir)**
Semua chat dari Rust Gateway disimpan di `PostgreSQL` tabel `messages`.
Setiap jam, Python Brain ngambil chat baru, di-embedding, masuk ke ChromaDB.
Ini yang bikin AI bisa jawab "tadi si Budi ngomongin apa?".

**Tier 3: Cold Memory (Selamanya - Tapi Di-Ringkas)**
Biar gak berat, chat yang udah lewat 30 hari gak disimpan mentah. Kita suruh LLM bikin rangkuman harian: "Pada 28 Agustus 2026, topik di #general adalah..."
Rangkumannya yang di-embedding. Jadi ingatannya selamanya ada, tapi ukurannya kecil.

> Penjelasan Vector DB buat pemula: Anggap aja ChromaDB itu kayak Google Drive khusus buat otak AI. Teks biasa diubah jadi angka (vektor) biar AI bisa cari kemiripan makna, bukan cuma keyword. Lu gak perlu setup server, cukup `pip install chromadb`.

### 4. Desain Server-State Awareness (Jawaban untuk Poin 2)

Ini yang paling penting. Rust harus ngasih "mata" ke Python.

Setiap request chat, Rust akan kirim JSON Context Injection seperti ini ke Python:

```json
{
  "prompt_user": "halo AI, siapa aja yang di VC?",
  "server_state": {
    "guild_name": "N-LIBRARY Server",
    "channel_name": "general",
    "author": { "name": "Budi", "roles": ["Member", "Gamer"], "id": "123" },
    "voice_state": {
      "in_voice": true,
      "channel": "Nongkrong",
      "participants": ["Budi", "Siti (deafen)", "Alata (playing Valorant)"],
      "activities": { "Alata": "Playing Valorant" }
    },
    "last_20_messages": [ "..." ]
  }
}
```

Di Python, ini kita sulap jadi System Prompt dinamis:
`Kamu adalah AI di server N-LIBRARY. User Budi dengan role Member sedang di channel general. Saat ini di VC Nongkrong ada... Jawab berdasarkan itu.`

### 5. Desain AI Agent & Tool Calling (Jawaban untuk Poin 3)

Python Brain gak cuma jawab teks, dia punya "tangan" buat bertindak lewat Rust.

Daftar Tools yang perlu kita bikin di FastAPI Rust:

1.  `tool_moderate`: `POST /api/moderate { user_id, action: "timeout/warn/delete", reason }` - Dipanggil kalo AI deteksi kata kasar / spam. AI belajar dari pola moderasi lu.
2.  `tool_music`: `POST /api/music { action: "play/skip/stop", query: "lagu" }` - Buat fitur "putar lagu X dong AI"
3.  `tool_role`: `POST /api/role { user_id, role_name, action: "add/remove" }` - Cek dulu apakah author punya permission Admin. Kalo gak, tolak.
4.  `tool_get_history`: `GET /api/history?channel=...&limit=50` - Buat AI baca history lebih dalam kalo perlu.
5.  `tool_get_server_info`: `GET /api/server_info` - Jumlah member, boost, dll.

Logika Agent di Python (LangChain Agent):
`User: "kasih role VIP ke Agus dong" -> LLM mikir: "Perlu cek apakah user adalah Admin, dan apakah role VIP ada" -> Panggil tool_role -> Rust eksekusi -> Balik "Done" -> LLM jawab "Siap, role VIP udah gue kasih ke Agus".`

### 6. Desain Voice Pipeline (Jawaban untuk Poin 4)

Lu mau Push-to-Talk + Wake Word, ini desain paling anti-error:

**Flow:**
1.  User ketik `!ai join` atau panggil bot masuk VC. Rust join pake Songbird.
2.  Rust standby, dengerin audio pake VAD (Silero VAD - model kecil buat deteksi suara manusia).
3.  Kalo ada suara, Rust rekam 5 detik, kirim ke Python `/api/stt`.
4.  Python STT pake `Groq Whisper (whisper-large-v3)` - Ini super cepat dan gratis via Groq, gak perlu Whisper lokal yang berat. Hasil teks dicek: apakah mengandung wake word? `["halo ai", "eh ai", "oi ai", "alata"]`. Kalo TIDAK ADA, buang.
5.  Kalo ADA wake word, buka Sesi 30 detik. Semua omongan setelah itu dianggap perintah.
6.  Teks perintah masuk ke Brain (RAG + Agent) -> Groq Llama 3.3 70B mikir (latency < 1 detik karena Groq) -> dapet jawaban teks.
7.  Teks jawaban dikirim ke TTS (`ElevenLabs` / `Coqui TTS` / `Groq PlayAI TTS`) -> jadi file .mp3 / PCM.
8.  Python kirim audio balik ke Rust `POST /api/play_tts`, Rust puter di VC.
9.  Kalo user bilang "udah diem" / "ai mute" / atau diam 30 detik, sesi ditutup, bot diem tapi tetep di VC.

Ini mencegah AI nyautin obrolan orang lain yang gak manggil dia.

### 7. Struktur Folder Baru (Dari Screenshot Lu)

Dari struktur lama:
```
- .env
- bot.py
- requirements.txt
```
Jadi:
```
N-LIBRARY/
├── .env.example (TIDAK PERNAH upload .env asli)
├── .gitignore (tambahin venv/, __pycache__, *.db, chroma_data/)
├── docker-compose.yml
├── rust_gateway/
│   ├── Cargo.toml (serenity, songbird, tokio, axum)
│   └── src/main.rs
├── python_brain/
│   ├── requirements.txt (fastapi, groq, chromadb, langchain, sentence-transformers, faster-whisper)
│   ├── app/
│   │   ├── main.py (FastAPI)
│   │   ├── llm/groq_client.py (Khusus buat Groq Llama)
│   │   ├── rag/ingestor.py
│   │   ├── agent/tools.py
│   │   └── voice/pipeline.py
│   └── knowledge/
│       ├── about_creator.md
│       └── about_bot.md
└── PLAN.md (file ini)
```

### 8. Roadmap Refactor - Step by Step buat Antigravity

**PHASE 0: Stabilisasi (Sekarang)**
- [ ] Fix `.env`: Ganti `YOUR_DISCORD_BOT_TOKEN_HERE` dengan token asli. Bikin `.env.example`.
- [ ] Pastikan `python bot.py` bisa online lagi tanpa error 401.
- [ ] Push ke GitHub dengan .gitignore yang bener.

**PHASE 1: Foundation & Logging (1-2 Minggu)**
- [ ] Setup PostgreSQL + tabel `messages`, `voice_logs`.
- [ ] Rust Gateway: Cukup log semua message event ke DB. Bot Python lama masih jalan.

**PHASE 2: Brain & RAG (2 Minggu)**
- [ ] Setup FastAPI Python Brain + ChromaDB.
- [ ] Bikin 3 file knowledge tentang diri lu.
- [ ] Endpoint `/chat` yang bisa jawab dengan context dari Rust (tanpa tool dulu).

**PHASE 3: Agent & Tool Calling (Paling Seru)**
- [ ] Bikin Internal API di Rust: `/api/role`, `/api/music`, `/api/moderate`.
- [ ] Implementasi Agent di Python yang bisa manggil tools itu.
- [ ] Fitur auto-moderasi kata kasar.

**PHASE 4: Voice Agent (Final Boss)**
- [ ] Integrasi Songbird receive audio.
- [ ] Implementasi Wake Word + Whisper + Silero VAD.
- [ ] Integrasi TTS (coba Coqui TTS dulu yang gratis, baru ElevenLabs).

**PHASE 5: Deploy**
- [ ] Bungkus semua pake Docker Compose biar jalan 1 perintah `docker-compose up`.

### 9. Keamanan & Config Baru (Groq Edition)

JANGAN PERNAH commit file `.env` asli. Di `.env.example` tulis gini:
```
TOKEN_DISCORD1=
GROQ_API_KEY= # Ganti API_TOKEN yang lama, ini buat Groq Llama
TMDB_KEY=
SAUCENAO=
```
Token asli cukup di local lu aja.

Kenapa Groq?
- Groq itu bukan model, tapi hardware super ngebut buat jalanin Llama. Jadi lu dapet Llama 3.3 70B Versatile (model terbaru Meta) dengan kecepatan 500+ tok/s.
- Free tier nya gak pelit, rate limit nya tinggi, jadi bisa dibilang "unlimited" buat proyek pribadi.
- Support Tool Calling / Function Calling native, jadi buat fitur `add role`, `play music` itu gampang banget di Groq.

---

**Next Action untuk lu:**
1. Setujuin plan ini.
2. Bikin 3 file `knowledge/*.md` tentang diri lu biar RAG nya ada isinya.
3. Kasih tau Antigravity: "Eksekusi PHASE 0 dulu".

Mau gue bikinin juga file `.env.example` dan `.gitignore` yang bener sekalian?
