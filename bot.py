import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from discord.ui import View, Select, Button
from typing import Optional
import yt_dlp
from collections import deque 
import asyncio 
import requests
import json
import base64
import aiohttp
import tempfile
import random, requests
import re
import pathlib

# List genre anime
genre_mapping = {
    "action": 1,
    "adventure": 2,
    "cars": 3,
    "comedy": 4,
    "dementia": 5,
    "demons": 6,
    "mystery": 7,
    "drama": 8,
    "ecchi": 9,
    "fantasy": 10,
    "game": 11,
    "hentai": 12,
    "historical": 13,
    "horror": 14,
    "kids": 15,
    "magic": 16,
    "martial arts": 17,
    "mecha": 18,
    "music": 19,
    "parody": 20,
    "samurai": 21,
    "romance": 22,
    "school": 23,
    "sci-fi": 24,
    "shoujo": 25,
    "shoujo ai": 26,
    "shounen": 27,
    "shounen ai": 28,
    "space": 29,
    "sports": 30,
    "super power": 31,
    "vampire": 32,
    "yaoi": 33,
    "yuri": 34,
    "harem": 35,
    "slice of life": 36,
    "supernatural": 37,
    "military": 38,
    "police": 39,
    "psychological": 40,
    "thriller": 41,
    "seinen": 42,
    "josei": 43,
    "award winning": 44,
    "gourmet": 45,
    "suspense": 46,
}

# Data Genre Manga
GENRE_MAP = {
    "action": 1,
    "adventure": 2,
    "comedy": 4,
    "mystery": 7,
    "drama": 8,
    "ecchi": 9,
    "fantasy": 10,
    "horror": 14,
    "magic": 16,
    "romance": 22,
    "school": 23,
    "sci-fi": 24,
    "shoujo": 25,
    "shounen": 27,
    "sports": 30,
    "supernatural": 32,
    "seinen": 41,
    "josei": 42,
    "thriller": 45
}

# Kategori Tokusatsu
TOKU_CATEGORIES = {
    "kamen rider": ["kamen rider"],
    "super sentai": ["sentai"],
    "ultraman": ["ultraman"],
    "metal hero": ["gavan", "sharivan", "shaider", "spielban", "juspion"],
    "garo": ["garo"],
    "gridman": ["gridman", "hyper agent"],
    "rescue hero": ["solbrain", "winspector", "rescuer"],
    "tokusatsu": ["tokusatsu"],  # kategori umum
}


# Header (buat nyimpen API atau lain sebagainya)
load_dotenv()
TOKEN = os.getenv("TOKEN_DISCORD1")
API_KEY = os.getenv("API_TOKEN")
TMDB = os.getenv("TMDB_KEY")
SAUCENEO = os.getenv("SAUCENAO")

SONG_QUEUES = {}

GUILD_ID = 1390706909434347600

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    test_guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync()
    print(f"{bot.user} telah aktif")

# Agar bisa menggunakan link musik
def extract_first_valid_track(data):
    if "url" in data:
        return data

    entries = data.get("entries")
    if entries:
        for item in entries:
            if not item:
                continue

            if "url" in item:
                return item
            
            formats = item.get("formats")
            if formats:
                for f in formats:
                    if "url" in f:
                        item["url"] = f["url"]
                        return item
    
    formats = data.get("formats")
    if formats:
        for f in formats:
            if "url" in f:
                data["url"] = f["url"]
                return data
    return None

# Fitur Help (Melihat apa saja commandnya)
@bot.tree.command(name = "bantuan", description = "Untuk melihat semua command")
async def help_command(interaction: discord.Integration):
    embed = discord.Embed(
        title = "**DAFTAR COMMAND N-LIBRARY**",
        description = "berikut adalah command yang digunakan pada n-library:",
        color = discord.Color.red()
    )
    
    embed.add_field(name="/mainkan <judul/link>", value="Memutar lagu berdasarkan judul atau link YouTube / YouTube Music", inline=False)
    embed.add_field(name="/lewati", value="Melewati lagu yang sedang diputar", inline=False)
    embed.add_field(name="/jeda", value="Menjeda lagu yang sedang berjalan", inline=False)
    embed.add_field(name="/lanjut", value="Melanjutkan lagu yang terjeda", inline=False)
    embed.add_field(name="/berhenti", value="Berhenti dan keluar dari voice channel", inline=False)
    embed.add_field(name="/asearch", value="untuk mencari tau informasi anime", inline=False)
    embed.add_field(name="/animejpg", value="mencari anime berdasarkan cuplikan gambar scene", inline=False)
    embed.add_field(name="/arekomendasi", value="rekomendasi anime, bisa random, atau berdasarkan genre", inline=False)
    embed.add_field(name="/fsearch", value="Mencari tau informasi pada film movies", inline=False)
    embed.add_field(name="/frekomendasi", value="rekomendasi film movies berdasarkan genre, kemiripan film, random", inline=False)
    embed.add_field(name="/drsearch", value="mencari tau informasi drama korea", inline=False)
    embed.add_field(name="/drrekomendasi", value="rekomendasi drakor, bisa random, atau berdasarkan genre", inline=False)
    embed.add_field(name="/tsearch", value="untuk mencari informasi terkait judul tokusatsu", inline=False)
    embed.add_field(name="/trekomendasi", value="Rekomendasi tokusatsu berdasarkan genre atau secara random", inline=False)
    embed.add_field(name="/autocode", value="untuk mengoding secara otomatis", inline=False)

    embed.set_footer(text="N-Library Bot by Alata")

    await interaction.response.send_message(embed=embed)

# MUSIK
# Untuk memainkan lagu 
@bot.tree.command(name = "mainkan", description= "lagu yang ingin dimainkan")
@app_commands.describe(song_query = "Judul musik yang ingin dimainkan")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("Kamu tidak ada di  voice channel")
        return  
    
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)
    
    ydl_option = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist":True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,

    }

    # agar bisa memasuki link yt music
    if song_query.startswith("http"):
        query = song_query
    else:
        query = f"ytsearch1:{song_query}"

    results = await search_ytdlp_async(query, ydl_option)
    first_track = extract_first_valid_track(results)
    
    if first_track is None:
        return await interaction.followup.send("Tidak dapat menemukan link tersebut :(")

    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")
    
    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()
    
    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Ditambahkan judul lagu: **{title}**")
    else:
        await interaction.followup.send(f"sekarang sedang memainkan musik: **{title}**")
        await play_next_song(voice_client, guild_id, interaction.channel)

# untuk mengskip lagu
@bot.tree.command(name = "lewati", description = "untuk skip lagu kesukaanmu")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Lewati lagu ini")
    else:
        await interaction.response.send_message("tidak memainkan lagu apapun untuk diskip")

# Untuk pause lagu
@bot.tree.command(name = "jeda", description = "untuk pause lagu kesukaanmu")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        return await interaction.response.send_message("aku tidak ada di voice channel")
        
    if not voice_client.is_playing():
        return await interaction.response.send_message("Tidak ada yang dimainkan")
            
        
    voice_client.pause()
    await interaction.response.send_message("Lagumu Berhenti!!")
    
# untuk resume lagu
@bot.tree.command(name = "lanjut", description = "untuk resume lagu kesukaanmu")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        return await interaction.response.send_message("aku tidak ada di voice channel")
        
    if not voice_client.is_paused():
        return await interaction.response.send_message("lagu ini tidak terpause!")
        
    voice_client.resume()
    await interaction.response.send_message("lagumu dilanjutkan")

# untuk disconneted lagu
@bot.tree.command(name = "berhenti", description = "untuk memberhentikan lagu kesukaanmu")
async def stop(interaction: discord.Interaction):
    await interaction.response.send_message("Berhenti memainkan lagu dan disconnected!!")

    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return
    
    guild_id_str = str(interaction.guild_id)

    # hapus antrean
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    # stop musik
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    # DISCONNECT DI BACKGROUND (tidak menunggu)
    asyncio.create_task(voice_client.disconnect(force=True))

# Proses mencari lagu
async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()  
        ffmpeg_option = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn -c:a libopus -b:a 96k",
        }

        source = discord.FFmpegOpusAudio(
             audio_url,
             **ffmpeg_option,
             executable="./ffmpeg"
        )
            
        def after_play(error):
            if error:
                print(f"{title} tidak ada dapat dimainkan: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after = after_play)
        asyncio.create_task(channel.send(f"Sedang memainkan musik: **{title}**"))

    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()

# ANIME
# Fitur search anime 
# total season
def count_seasons(anime_list, base_title):
    total = 0
    for item in anime_list:
        title = item.get("title", "").lower()
        
        if base_title.lower() in title:
            if "season" in title:
                # ambil angka season
                parts = title.split("season")
                try:
                    season_num = int(parts[1].strip().split()[0])
                    total = max(total, season_num)
                except:
                    pass
            else:
                # ini biasanya season 1
                total = max(total, 1)
    
    return total

@bot.tree.command(name = "asearch", description = "rekomendasi anime")
@app_commands.describe(judul = "Judul Anime")
async def anime_info(interaction: discord.Interaction, judul: str):
    await interaction.response.defer()

    apianime = f"https://api.jikan.moe/v4/anime?q={requests.utils.requote_uri(judul)}&limit=10"
   
    
    try:
        resp = requests.get(apianime, timeout = 10)
    except requests.RequestException as e:
        await interaction.followup.send("Gagal menghubungi API. coba lagi nanti")
        print("Request error ke Jikan API")
        return
    
    if resp.status_code != 200:
        await interaction.followup.send(f"API mengembalikan status {resp.status_code}.coba lagi nanti")
        return
    
    data = resp.json()
    if not data.get("data"):
        await interaction.followup.send("Anime tidak ditemukan :(")
        return
    
    anime_list = data["data"]
    total_season = count_seasons(anime_list, judul)

    kartun = anime_list[0]


    title = kartun.get("title", "Unknown")
    score = kartun.get("score", "N/A")
    episodes = kartun.get("episodes", "N/A")
    season = kartun.get("season", "Unknown")
    year = kartun.get("year", "N/A")
    synopsis_full = kartun.get("synopsis") or "Tidak ada sinopsis"
    synopsis = (synopsis_full[:300] + "...") if len(synopsis_full) > 300 else synopsis_full
    image = None
    images = kartun.get("images") or {}
    jpg = images.get("jpg") if isinstance(images, dict) else None
    if jpg:
        image = jpg.get("large_image_url")
    otk_url = f"https://otakudesu.best/?s={requests.utils.requote_uri(title)}&post_type=anime"

    embed = discord.Embed(
        title = title,
        description = synopsis,
        color = discord.Color.red()
    )

    embed.add_field(name = "Skor", value = str(score), inline = True)
    embed.add_field(name = "Episode", value = str(episodes), inline = True)
    embed.add_field(name = "Year", value = f"{season.capitalize()}{year}", inline = True)
    embed.add_field(name = "Total Season", value = f"{total_season} Season", inline = True)
    embed.add_field(name = "Link Nonton", value = otk_url, inline = False)
    if image:
        embed.set_image(url = image)

    await interaction.followup.send(embed = embed)

# Search anime menggunakan scene gambar
@bot.tree.command(name = "animejpg", description = "untuk mencari judul anime menggunaka cuplikan gambar anime")
@app_commands.describe(gambar = "Upload Gambar atau Screenshot scene anime")
async def anime_search(interaction: discord.Interaction, gambar: discord.Attachment):
    await interaction.response.defer()

    if not gambar.content_type.startswith("image/"):
        return await interaction.followup.send("file harus berupa gambar !!")
    
    img_bytes = await gambar.read()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    api_url = "https://api.trace.moe/search"
    
    headers = {
        "User-Agent": "Mozilla/5.0",
        
    }

    files = {
        "image":img_bytes
    }

    try:
        resp = requests.post(api_url, headers=headers, files=files, timeout = 20)
        
        print("STATUS:", resp.status_code)
        print("RAW RESPONSE:", resp.text[:200])

        result = resp.json()
    except Exception as e:
        print("Error:", e)
        return await interaction.followup.send("Gagal menghubungi API, coba lagi")
    
    if "result" not in result or len(result["result"]) == 0:
        return await interaction.followup.send("Tidak ditemukan berdasarkan anime pada gambar itu:(")
    
    info = result["result"][0]

    title = info.get("filename") or info.get("anime", "Unknown")
    episode = info.get("episode", "??")
    similarity = round(info.get("similarity", 0) * 100, 2)
    from_time = info.get("from", 0)
    to_time = info.get("to", 0)
    preview = info.get("video")
    if preview:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(preview) as video_resp:
                    if video_resp.status == 200:
                        with tempfile.NamedTemporaryFile(delete = False, suffix = ".mp4") as tmp:
                            tmp.write(await video_resp.read())
                            temp_path = tmp.name
                        
                        await interaction.followup.send(file = discord.File(temp_path, filename = "preview.mp4"))
                        os.remove(temp_path)
                    else:
                        await interaction.followup.send("Gagal mengambil video preview")
        except Exception as e:
            print("Video error", e)
            await interaction.followup.send("Terjadi kesalahan mengambil Video Preview")

    image_preview = info.get("image")

    def time_format(sec):
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m:02}:{s:02}"
    
    time_range = f"{time_format(from_time)} - {time_format(to_time)}"

    embed = discord.Embed(
        title = f"Hasil pencarian Scene",
        description=f"Ditemukan anime berdasarkan screenshot!",
        color=discord.Color.red()
    )

    embed.add_field(name = "Anime", value = title, inline = False)
    embed.add_field(name = "Episode", value = str(episode), inline = True)
    embed.add_field(name = "Similarity", value = f"{similarity}%", inline = True)
    embed.add_field(name = "Waktu Scene", value = time_range, inline = True)
    if preview:
        embed.add_field(name = "Preview Video", value = preview, inline = False)
    if image_preview:
        embed.set_image(url = image_preview)
    await interaction.followup.send(embed = embed)

# Rekomendasi Anime 
@bot.tree.command(name="arekomendasi", description="Rekomendasi anime berdasarkan genre (opsional). Jika kosong → random genre.")
@app_commands.describe(genre="Genre anime (optional). Jika tidak diisi akan random genre).")
async def anime_rekomendasi(interaction: discord.Interaction, genre: str | None = None):
    await interaction.response.defer()

    if genre is None:
        genre = random.choice(list(genre_mapping.keys()))
        is_random = True
    else:
        genre = genre.lower().strip()
        if genre not in genre_mapping:
            daftar_genre = ", ".join(g.capitalize() for g in genre_mapping.keys())
            return await interaction.followup.send(
                f"Genre **{genre}** tidak ditemukan!\n\n"
                f"**Daftar genre:**\n{daftar_genre}"
            )
        is_random = False

    genre_id = genre_mapping[genre]

    api_url = f"https://api.jikan.moe/v4/anime?genres={genre_id}&order_by=score&sort=desc&limit=25"

    try:
        response = requests.get(api_url, timeout=10).json()
    except:
        return await interaction.followup.send("Gagal menghubungi API Jikan!")

    # Jikan API kadang kasih data kosong → random ulang
    if "data" not in response or not response["data"]:
        return await interaction.followup.send(
            f"Tidak ada anime ditemukan untuk genre **{genre}**.\n"
            f"Mungkin API Jikan sedang limit."
        )

    anime = random.choice(response["data"])

    title = anime.get("title", "Unknown")
    score = anime.get("score", "N/A")
    eps = anime.get("episodes", "N/A")
    synopsis = anime.get("synopsis", "Tidak ada sinopsis...")
    if len(synopsis) > 300:
        synopsis = synopsis[:300] + "..."

    image = anime.get("images", {}).get("jpg", {}).get("large_image_url")

    embed = discord.Embed(
        title=f"Rekomendasi Genre: {genre.capitalize()}",
        description=synopsis,
        color=discord.Color.red()
    )

    embed.add_field(name="Judul", value=title, inline=False)
    embed.add_field(name="Skor", value=str(score), inline=True)
    embed.add_field(name="Episode", value=str(eps), inline=True)
    if image:
        embed.set_image(url=image)

    await interaction.followup.send(embed=embed)

# FILM
# Search FILM
@bot.tree.command(name = "fsearch", description = "mencari informasi film berdasarkan judul")
@app_commands.describe(judul = "Judul film yang ingin dicari.")
async def film_search(interaction: discord.Interaction, judul: str):
    await interaction.response.defer()

    if TMDB is None:
        return await interaction.followup.send("TMDB Key tidak ditemukan")
    
    query = requests.utils.requote_uri(judul)
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB}&query={query}&language=id-ID"

    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
    except:
        return await interaction.followup.send("Gagal menghubungi API")
    
    if "results" not in data or len(data["results"]) == 0:
        return await interaction.followup.send(f"Film **{judul}** tidak ditemukan.")

    film = data["results"][0]
    title = film.get("title", "Tidak ada judul")
    overview = film.get("overview", "Tidak ada deskripsi.")
    if len(overview) > 350:
        overview = overview[:350] + "..."
    rating = film.get("vote_average", "N/A")
    release = film.get("release_date", "N/A")
    popularity = film.get("popularity", "N/A")
    poster_path = film.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview,
        color=discord.Color.red()
    )

    embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
    embed.add_field(name="📅 Rilis", value=str(release), inline=True)
    embed.add_field(name="🔥 Popularitas", value=str(popularity), inline=True)

    if poster_url:
        embed.set_image(url=poster_url)
        
    await interaction.followup.send(embed=embed)

# Rekomendasi FILM
@bot.tree.command(name = "frekomendasi", description = "Rekomendasi film")
@app_commands.describe(
    mode="Pilih mode rekomendasi: judul atau genre",
    judul="Judul film acuan (opsional, hanya untuk mode judul)",
    genre="Genre film (opsional, hanya untuk mode genre)"
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="judul", value="judul"),
        app_commands.Choice(name="genre", value="genre"),
    ]
)
async def film_rekomendasi(
    interaction: discord.Interaction,
    mode: app_commands.Choice[str],
    judul: str | None = None,
    genre: str | None = None
):
    await interaction. response.defer()
    
    if TMDB is None:
        return await interaction.followup.send("API tidak ditemukan")
    
    # Mode Random
    mode_value = mode.value if mode else "random"

    if mode_value == "random":
        url = (
            f"https://api.themoviedb.org/3/discover/movie?"
            f"api_key={TMDB}&sort_by=popularity.desc&language=id-ID"
        )
    
        try:
            data = requests.get(url, timeout=10).json()
        except:
            return await interaction.followup.send("Gagal menghubungi API TMDB.")
    
        if "results" not in data or len(data["results"]) == 0:
            return await interaction.followup.send("film tidak ditemukan")
    
        rekom = random.choice(data["results"])
        title = rekom.get("title", "Tidak ada judul")
        overview = rekom.get("overview", "Tidak ada deskripsi.")
        overview = (overview[:350] + "...") if len(overview) > 350 else overview
        rating = rekom.get("vote_average", "N/A")
        release = rekom.get("release_date", "N/A")
        popularity = rekom.get("popularity", "N/A")
        poster_path = rekom.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        embed = discord.Embed(
            title="🎲 Rekomendasi Film Random",
            description=overview,
            color=discord.Color.red()
        )

        embed.add_field(name="Judul", value=title, inline=False)
        embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
        embed.add_field(name="📅 Rilis", value=str(release), inline=True)
        embed.add_field(name="🔥 Popularitas", value=str(popularity), inline=True)

        if poster_url:
            embed.set_image(url=poster_url)

        return await interaction.followup.send(embed=embed)


    # Mode judul
    if mode.value == "judul":
        if judul is None:
            return await interaction.followup.send(
                "Untuk mode **judul**, kamu harus mengisi param `judul`."
            )
        query = requests.utils.requote_uri(judul)
        search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB}&query={query}&language=id-ID"
    
        try:
            resp = requests.get(search_url, timeout=10)
            data = resp.json()
        except:
            return await interaction.followup.send("Gagal menghubungi API")
    
        if "results" not in data or len(data["results"]) == 0:
            return await interaction.followup.send(f"Film **{judul}** tidak ditemukan.")
    
        movie_id = data["results"][0]["id"]
        film_title = data["results"][0]["title"]


        rec_url = f"https://api.themoviedb.org/3/movie/{movie_id}/recommendations?api_key={TMDB}&language=id-ID"
        rec_resp = requests.get(rec_url, timeout=10)
        rec_data = rec_resp.json()
        if "results" not in rec_data or len(rec_data["results"]) == 0:
            return await interaction.followup.send(
                f"Tidak ada rekomendasi untuk film **{film_title}**."
            )
        rekom = random.choice(rec_data["results"])
    
        title = rekom.get("title", "Tidak ada judul")
        overview = rekom.get("overview", "Tidak ada deskripsi.")
        if len(overview) > 350:
            overview = overview[:350] + "..."

        rating = rekom.get("vote_average", "N/A")
        release = rekom.get("release_date", "N/A")
        popularity = rekom.get("popularity", "N/A")
        poster_path = rekom.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        embed = discord.Embed(
            title=f"🎥 Rekomendasi Mirip: {film_title}",
            description=overview,
            color=discord.Color.red()
        )

        embed.add_field(name="Judul", value=title, inline=False)
        embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
        embed.add_field(name="📅 Rilis", value=str(release), inline=True)
        embed.add_field(name="🔥 Popularitas", value=str(popularity), inline=True)
        if poster_url:
            embed.set_image(url=poster_url)
        return await interaction.followup.send(embed=embed)

    # Mode genre
    if mode.value == "genre":
        if genre is None:
            return await interaction.followup.send(
                "Untuk mode **genre**, kamu harus mengisi param `genre`."
            )
        
        genre_url = f"https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB}&language=id-ID"
        genre_resp = requests.get(genre_url).json()
        genre_map = {g["name"].lower(): g["id"] for g in genre_resp["genres"]}

        if genre.lower() not in genre_map:
            daftar = ",".join(genre_map.keys())
            return await interaction.followup.send(
                f"Genre **{genre}** tidak ditemukan.\nDaftar genre:\n{daftar}"
            )
        
        gid = genre_map[genre.lower()]
        rec_url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB}&with_genres={gid}&language=id-ID&sort_by=popularity.desc"
        rec_data = requests.get(rec_url).json()

        if "results" not in rec_data or len(rec_data["results"]) == 0:
            return await interaction.followup.send(f"Tidak ada rekomendasi untuk genre **{genre}**.")

        rekom = random.choice(rec_data["results"])

        title = rekom.get("title", "Tidak ada judul")
        overview = rekom.get("overview", "Tidak ada deskripsi.")
        if len(overview) > 350:
            overview = overview[:350] + "..."

        rating = rekom.get("vote_average", "N/A")
        release = rekom.get("release_date", "N/A")
        popularity = rekom.get("popularity", "N/A")
        poster_path = rekom.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        embed = discord.Embed(
            title=f"🎬 Rekomendasi Genre: {genre.capitalize()}",
            description=overview,
            color=discord.Color.red()
        )

        embed.add_field(name="Judul", value=title, inline=False)
        embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
        embed.add_field(name="📅 Rilis", value=str(release), inline=True)
        embed.add_field(name="🔥 Popularitas", value=str(popularity), inline=True)

        if poster_url:
            embed.set_image(url=poster_url)
            
        return await interaction.followup.send(embed=embed)

# DRAMA KOREA
# Search Drakor series / Movie
@bot.tree.command(name = "drsearch", description = "mencari informasi series/movie drama korea")
@app_commands.describe(judul = "judul dari drama korea (drakor)")
async def drakor_search(interaction: discord.Interaction, judul: str):
    await interaction.response.defer()

    if TMDB is None:
        return await interaction.followup.send("API tidak ditemukan")

    query = requests.utils.requote_uri(judul)
    tv_url = (
        f"https://api.themoviedb.org/3/search/tv?"
        f"api_key={TMDB}&language=id-ID&query={query}"
        f"&with_original_language=ko"
    )
    tv_data = requests.get(tv_url).json()

    movie_url = (
        f"https://api.themoviedb.org/3/search/movie?"
        f"api_key={TMDB}&language=id-ID&query={query}"
        f"&with_original_language=ko"
    )

    movie_data = requests.get(movie_url).json()

    tv_result = tv_data["results"][0] if tv_data.get("results") else None
    movie_result = movie_data["results"][0] if movie_data.get("results") else None

    if not tv_result and not movie_result:
        return await interaction.followup.send(f"'{judul}' tidak ditemukan sebagai drakor maupun film Korea.")

    if tv_result and not movie_result:
        chosen = tv_result
        jenis = "Drama Korea Series"
    elif movie_data and not tv_result:
        chosen = movie_result
        jenis = "Drama Korea Movies"
    else:
        if tv_result["vote_average"] >= movie_result["vote_average"]:
            chosen = tv_result
            jenis = "Drama Korea Series"
        else:
            chosen = movie_result
            jenis = "Drama Korea Movies"
    
    title = chosen.get("name") or chosen.get("title") or "Tidak ada judul"
    overview = chosen.get("overview", "Tidak ada deskripsi.")
    if len(overview) > 350:
        overview = overview[:350] + "..."
    rating = chosen.get("vote_average", "N/A")
    release = chosen.get("first_air_date") or chosen.get("release_date") or "N/A"
    poster = chosen.get("poster_path")

    embed = discord.Embed(
        title=f"🎬 {jenis}: {title}",
        description=overview,
        color=discord.Color.red()
    )

    embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
    embed.add_field(name="📅 Rilis", value=str(release), inline=True)
    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    return await interaction.followup.send(embed=embed)

# Rekomendasi Drakor
@bot.tree.command(name = "drrekomendasi", description = "Rekomendasi drama korea")
@app_commands.describe(genre = "Genre dari drakor (Opsional)")
async def drakor_rekomendasi(interaction: discord.Interaction, genre: str | None = None):
    await interaction.response.defer()

    if TMDB is None:
        return await interaction.followup.send("API Tidak Ditemukan")
    
    # Random
    if genre is None:
        url = (
            f"https://api.themoviedb.org/3/discover/tv?"
            f"api_key={TMDB}&language=id-ID&with_original_language=ko&sort_by=popularity.desc"
        )

        data_tv = requests.get(url).json()

        url_movie = (
            f"https://api.themoviedb.org/3/discover/movie?"
            f"api_key={TMDB}&language=id-ID&with_original_language=ko&sort_by=popularity.desc"
        )

        data_movie = requests.get(url_movie).json()

        all_result = []

        if data_tv.get("results"):
            all_result.extend(data_tv["results"])
        
        if data_movie.get("results"):
            all_result.extend(data_movie["results"])
        
        if not all_result:
            return await interaction.followup.send("Rekomendasi tidak ditemukan")

        rekom = random.choice(all_result)

        title = rekom.get("name") or rekom.get("title") or "Tidak ada judul"
        overview = rekom.get("overview", "Tidak ada deskripsi")
        if len(overview) > 350:
            overview = overview[:350] + "..."

        rating = rekom.get("vote_average", "N/A")
        release = rekom.get("first_air_date") or rekom.get("release_date") or "N/A"
        poster = rekom.get("poster_path")

        embed = discord.Embed(
            title=f"🎲 Rekomendasi Drakor Random",
            description=overview,
            color=discord.Color.red()
        )

        embed.add_field(name="Judul", value=title, inline=False)
        embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
        embed.add_field(name="📅 Rilis", value=str(release), inline=True)

        if poster:
            embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

        return await interaction.followup.send(embed=embed)

    # Genre
    genre = genre.lower().strip()
    genre_tv_url = f"https://api.themoviedb.org/3/genre/tv/list?api_key={TMDB}&language=id-ID"
    genre_tv_data = requests.get(genre_tv_url).json()
    genre_movie_url = f"https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB}&language=id-ID"
    genre_movie_data = requests.get(genre_movie_url).json()

    genre_map = {}
    for g in genre_tv_data.get("genres", []):
        genre_map[g["name"].lower()] = g["id"]
    for g in genre_movie_data.get("genres", []):
        genre_map[g["name"].lower()] = g["id"]
    
    if genre not in genre_map:
        daftar = ", ".join(genre_map.keys())
        return await interaction.followup.send(
            f"Genre **{genre}** tidak ditemukan!\n\nDaftar genre valid:\n{daftar}"
        )
    
    genre_id = genre_map[genre]

    tv_url = (
        f"https://api.themoviedb.org/3/discover/tv?"
        f"api_key={TMDB}&language=id-ID&with_original_language=ko"
        f"&with_genres={genre_id}&sort_by=popularity.desc"
    )
    tv_data = requests.get(tv_url).json()

    movie_url = (
        f"https://api.themoviedb.org/3/discover/movie?"
        f"api_key={TMDB}&language=id-ID&with_original_language=ko"
        f"&with_genres={genre_id}&sort_by=popularity.desc"
    )
    movie_data = requests.get(movie_url).json()

    all_result = []
    if tv_data.get("results"):
        all_result.extend(tv_data["results"])

    if movie_data.get("results"):
        all_result.extend(movie_data["results"])
    
    if not all_result:
         return await interaction.followup.send(f"Tidak ada drakor genre **{genre}** ditemukan.")
    
    rekom = random.choice(all_result)

    title = rekom.get("name") or rekom.get("title") or "Tidak ada judul"
    overview = rekom.get("overview", "Tidak ada deskripsi")
    if len(overview) > 350:
        overview = overview[:350] + "..."

    rating = rekom.get("vote_average", "N/A")
    release = rekom.get("first_air_date") or rekom.get("release_date") or "N/A"
    poster = rekom.get("poster_path")

    embed = discord.Embed(
        title=f"🎬 Rekomendasi Drakor Genre: {genre.capitalize()}",
        description=overview,
        color=discord.Color.red()
    )

    embed.add_field(name="Judul", value=title, inline=False)
    embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
    embed.add_field(name="📅 Rilis", value=str(release), inline=True)

    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    return await interaction.followup.send(embed=embed)

# MANGA
# Pencarian manga dan link official
@bot.tree.command(name = "msearch", description = "untuk mencari informasi manga sekaligus link baca")
@app_commands.describe(judul = "judul dari manga tersebut")
async def manga_search(interaction: discord.Interaction, judul: str):
    await interaction.response.defer()

    query = requests.utils.requote_uri(judul)
    url = f"https://api.jikan.moe/v4/manga?q={query}&limit=10"

    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
    except Exception as e:
        print("msearch error")
        return await interaction.followup.send("Gagal menghubungi API")
    
    if not data.get("data"):
        return await interaction.followup.send(f"Manga **{judul}** tidak ditemukan!!")

    manga = data["data"][0]

    title = manga.get("title") or manga.get("title_english") or "tidak ada judul"
    synopsis = manga.get("synopsis") or "tidak ada sinopsis"
    if synopsis and len(synopsis) > 300:
        synopsis = synopsis[:300] + "..."
    volumes = manga.get("volumes", "N/A")
    chapters = manga.get("chapters", "N/A")
    score = manga.get("score", "N/A")
    mal_url = manga.get("url")

    md_search_url = f"https://mangadex.org/titles?q={requests.utils.requote_uri(title)}"

    image = None
    if manga.get("images") and manga["images"].get("jpg"):
        image = manga["images"]["jpg"].get("large_image_url")
    
    embed = discord.Embed(
        title=f"📚 {title}",
        description=synopsis,
        color=discord.Color.red()
    )

    embed.add_field(name="⭐ Skor", value=str(score), inline=True)
    embed.add_field(name="📘 Volumes", value=str(volumes), inline=True)
    embed.add_field(name="📄 Chapters", value=str(chapters), inline=True)

    if mal_url:
        embed.add_field(name="🔗 MAL Link", value=mal_url, inline=False)

    # link baca legal
    embed.add_field(name="📖 Baca di MangaDex", value=md_search_url, inline=False)

    if image:
        embed.set_image(url=image)

    await interaction.followup.send(embed=embed)

# rekomendasi manga
@bot.tree.command(name = "mrekomendasi", description = "rekomendasi manga berdasarkan genre atau secara acak")
@app_commands.describe(genre = "Genre dari manga tersebut")
async def manga_rekom(interaction: discord.Interaction, genre: str = None):
    await interaction.response.defer()

    if genre:
        genre_key = genre.lower()
        if genre_key not in GENRE_MAP:
            return await interaction.followup.send(f"Genre **{genre}** tidak valid!")
        
        genre_id = GENRE_MAP[genre_key]
        url = f"https://api.jikan.moe/v4/manga?genres={genre_id}&limit=25"
    else:
        url = "https://api.jikan.moe/v4/random/manga"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
    except Exception as e:
        print("mrekom error", e)
        return await interaction.followup.send("Gagal menghubungi API rekomendasi.")
    
    if genre:
        if not data.get("data"):
            return await interaction.followup.send(f"Tidak ada manga ditemukan untuk genre **{genre}** 😿")
        manga = random.choice(data["data"])
    else:
        manga = data.get("data", {})
    
    title = manga.get("title") or "Tidak ada judul"
    synopsis = manga.get("synopsis") or "Tidak ada sinopsis."
    if len(synopsis) > 300:
        synopsis = synopsis[:300] + "..."

    score = manga.get("score", "N/A")
    volumes = manga.get("volumes", "N/A")
    chapters = manga.get("chapters", "N/A")
    md_search = f"https://mangadex.org/titles?q={requests.utils.requote_uri(title)}"
    image = manga.get("images", {}).get("jpg", {}).get("large_image_url")

    embed = discord.Embed(
        title=f"📘 Rekomendasi Manga: {title}",
        description=synopsis,
        color=discord.Color.red()
    )

    embed.add_field(name="⭐ Skor", value=str(score), inline=True)
    embed.add_field(name="📘 Volumes", value=str(volumes), inline=True)
    embed.add_field(name="📄 Chapters", value=str(chapters), inline=True)
    if genre:
        embed.add_field(name="🎭 Genre", value=genre, inline=False)
    embed.add_field(name="📖 Baca di MangaDex", value=md_search, inline=False)
    if image:
        embed.set_image(url=image)

    await interaction.followup.send(embed=embed)

# search manga melalui potongan panel
@bot.tree.command(name = "mangajpg", description = "mencari manga dari cuplikan/potongan panel")
@app_commands.describe(gambar = "Upload cuplikan panel manga")
async def search_image(interaction: discord.Interaction, gambar: discord.Attachment):
    await interaction.response.defer()

    if not gambar.content_type.startswith("image/"):
        return await interaction.followup.send("file harus berupa panel manga!")
    
    img_bytes = await gambar.read()
    if not SAUCENEO:
        return await interaction.followup.send("API tidak ditemukan")
    
    url = (
        f"https://saucenao.com/search.php?"
        f"output_type=2&numres=5&db=999&api_key={SAUCENEO}"
    )

    files = {"file": ("image.jpg", img_bytes)}

    try:
        resp = requests.post(url, files=files, timeout=20)
        data = resp.json()
    except Exception as e:
        print("Error SauceNeo", e)
        return await interaction.followup.send("Gagal menghubungi API SauceNAO!")

    if "results" not in data or len(data["results"]) == 0:
        return await interaction.followup.send("Tidak ditemukan manga berdasarkan gambar ini")
    
    result = data["results"][0]
    header = result.get("header", {})
    info = result.get("data", {})

    similarity = header.get("similarity", "0")
    title = info.get("title") or info.get("source") or "Tidak ada judul"
    part = info.get("part", "N/A")
    page = info.get("page", "N/A")
    eng_name = info.get("eng_name", "")
    jp_name = info.get("jp_name", "")
    danbooru = info.get("ext_urls", [None])[0]

    embed = discord.Embed(
        title="📘 Hasil Pencarian Manga (Panel Image)",
        description=f"Ditemukan berdasarkan panel gambar!",
        color=discord.Color.green()
    )

    embed.add_field(name="Judul", value=title, inline=False)
    if eng_name:
        embed.add_field(name="Judul Inggris", value=eng_name, inline=False)
    if jp_name:
        embed.add_field(name="Judul Jepang", value=jp_name, inline=False)

    embed.add_field(name="Chapter", value=str(part), inline=True)
    embed.add_field(name="Halaman", value=str(page), inline=True)
    embed.add_field(name="Similarity", value=f"{similarity}%", inline=True)
    if danbooru:
        embed.add_field(name="Link Sumber", value=danbooru, inline=False)
    preview_img = header.get("thumbnail") or info.get("thumbnail") or header.get("preview")
    if preview_img:
        embed.set_image(url=preview_img)

    await interaction.followup.send(embed=embed)

# TOKUSATSU
# Search Tokusatsu
@bot.tree.command(name = "tsearch", description = "Cari informasi terkait tokusatsu")
@app_commands.describe(judul = "judul tokusatsu")  
async def toku_search(interaction: discord.Interaction, judul: str):
    await interaction.response.defer()

    if not TMDB:
        return await interaction.followup.send("API Tidak ditemukan")
    
    url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB}&query={judul}"
    response = requests.get(url).json()

    if "results" not in response or len(response["results"]) == 0:
        return await interaction.followup.send(f"Tokusatsu **{judul}** tidak ditemukan 😿")
    
    result = response["results"][0]

    title = result.get("name", "Tidak ada judul")
    overview = result.get("overview", "Tidak ada ringkasan.")
    rating = result.get("vote_average", 0)
    first_air = result.get("first_air_date", "Unknown")
    poster_path = result.get("poster_path", None)
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    ry_url = f"https://ryuzakilogia.net/?s={requests.utils.requote_uri(title)}"

    embed = discord.Embed(
        title=f"📺 Tokusatsu: {title}",
        description=overview[:300] + ("..." if len(overview) > 300 else ""),
        color=discord.Color.red()
    )
    
    embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
    embed.add_field(name="📅 Tahun Tayang", value=first_air, inline=True)
    embed.add_field(name = "Link Nonton:", value = ry_url, inline = False)
    if poster_url:
        embed.set_image(url=poster_url)

    await interaction.followup.send(embed=embed)

# Rekomendasi Tokusatsu
@bot.tree.command(name = "trekomendasi", description = "rekomendasi film tokusatsu")
@app_commands.describe(kategori = "Kategori pada tokusatsu seperti kamen rider, super sentai dll")
async def toku_rekomendasi(interaction: discord.Interaction, kategori: Optional[str] = None):
    await interaction.response.defer()
    
    if not TMDB:
        return await interaction.followup.send("API tidak ditemukan")
    
    if kategori is None:
        kategori = "random"
    
    kategori = kategori.lower().strip()

    if kategori == "random":
        kategori = random.choice(list(TOKU_CATEGORIES.keys()))
    
    if kategori not in TOKU_CATEGORIES:
        daftar = ", ".join(TOKU_CATEGORIES.keys())
        return await interaction.followup.send(
            f"Kategori **{kategori}** tidak ada!\n\nKategori tersedia:\n{daftar}"
        )
    
    keyword = random.choice(TOKU_CATEGORIES[kategori])

    url = (
        f"https://api.themoviedb.org/3/search/tv?"
        f"api_key={TMDB}&query={requests.utils.requote_uri(keyword)}&language=en-US"
    )

    try:
        data = requests.get(url, timeout=10).json()
    except:
        return await interaction.followup.send("Gagal menghubungi API TMDB!")

    if "results" not in data or len(data["results"]) == 0:
        return await interaction.followup.send( f"Tidak ada data tokusatsu untuk kategori **{kategori}**.")

    rekom = random.choice(data["results"])

    title = rekom.get("name", "Tidak ada judul")
    overview = rekom.get("overview", "Tidak ada deskripsi.")
    if len(overview) > 350:
        overview = overview[:350] + "..."

    rating = rekom.get("vote_average", "N/A")
    release = rekom.get("first_air_date", "N/A")

    poster = rekom.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None

    # link nonton
    ry_url = f"https://ryuzakilogia.net/?s={requests.utils.requote_uri(title)}"

    embed = discord.Embed(
        title=f"⚡ Rekomendasi Tokusatsu: {kategori.upper()}",
        description=overview,
        color=discord.Color.red()
    )

    embed.add_field(name="Judul", value=title, inline=False)
    embed.add_field(name="⭐ Rating", value=str(rating), inline=True)
    embed.add_field(name="📅 Tahun", value=str(release), inline=True)
    embed.add_field(name="🔗 Link Nonton", value=ry_url, inline=False)

    if poster_url:
        embed.set_image(url=poster_url)

    await interaction.followup.send(embed=embed)

# KODING
@bot.tree.command(name = "autocode", description = "Generate kode otomatis")
@app_commands.describe(
    language="Bahasa pemrograman (python, javascript, go, java, etc.)",
    description="Deskripsikan apa yang mau dibuat (fungsi, modul, app, dll).",
    filename="Nama file output (opsional). contoh: app.py",
    multiple_files="Jika ya, coba buat beberapa file (jika relevan)"
)
async def autocode(
    interaction: discord.Interaction,
    language: str,
    description: str,
    filename: Optional[str] = None,
    multiple_files: Optional[bool] = False
):
    await interaction.response.defer()
    
    if not API_KEY:   
        return await interaction.followup.send("API key untuk OpenRouter / model tidak ditemukan.")

    def safe_filename(name: str, default_ext: str):
        name = name.strip()
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        if "." not in name:
            name = name + default_ext
        return name
    
    language_lower = language.lower().strip()
    ext_map = {
        "python": ".py",
        "py": ".py",
        "javascript": ".js",
        "js": ".js",
        "typescript": ".ts",
        "ts": ".ts",
        "go": ".go",
        "java": ".java",
        "csharp": ".cs",
        "c#": ".cs",
        "cpp": ".cpp",
        "c++": ".cpp",
        "ruby": ".rb",
        "php": ".php",
        "bash": ".sh",
        "shell": ".sh",
        "html": ".html",
        "css": ".css",
    }
    default_ext = ext_map.get(language.lower, "txt")

    system_prompt = (
        "Kamu adalah code generator yang hanya mengembalikan kode. "
        "Jika diminta menghasilkan beberapa file, gunakan format berikut:\n\n"
        "~~~file: path/to/file1.ext\n<isi file1>\n~~~endfile\n~~~file: path/to/file2.ext\n<isi file2>\n~~~endfile\n\n"
        "Jika hanya satu file, cukup berikan isi file dalam satu blok kode tanpa penjelasan panjang. "
        "Jangan sertakan penjelasan di luar blok file. Jawaban harus dalam bahasa kode yang diminta."
    )

    user_prompt = (
        f"Bahasa: {language}\n"
        f"Deskripsi: {description}\n"
        f"Generate {'beberapa file' if multiple_files else 'satu file'}."
        f"\nBerikan juga komentar singkat header (1-2 baris) di bagian atas file jika perlu."
        "\nJangan sertakan instruksi instalasi panjang atau penjelasan. Balas hanya file-file sesuai format."
    )

    payload = {
        "model": "meta-llama/llama-3-8b-instruct",  # pakai model yang sama seperti fitur chatbot
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1600
    }

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
    except Exception as e:
        print("autocode error:", e)
        return await interaction.followup.send("Gagal menghasilkan kode (API error). Coba lagi nanti.")

    file_pattern = re.compile(r"~~~file:\s*(?P<path>[^\n]+)\n(?P<content>.*?)~~~endfile", re.DOTALL)
    files = []
    for m in file_pattern.finditer(raw_text):
        path = m.group("path").strip()
        content = m.group("content").strip()
        files.append((path, content))
    
    if not files:
        code_block = None
        m = re.search(r"```(?:\w+)?\n(.*?)```", raw_text, re.DOTALL)
        if m:
            code_block = m.group(1).strip()
        else:
            code_block = raw_text.strip()
        
        out_name = filename or f"autogen{default_ext}"
        out_name = safe_filename(out_name, default_ext)
        files.append((out_name, code_block))

    sent_files = []
    tmp_paths = []
    try:
        for path, content in files:
            # ensure extension
            p = pathlib.Path(path)
            if not p.suffix:
                path = str(p) + default_ext
            safe_name = safe_filename(path, default_ext)

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=pathlib.Path(safe_name).suffix)
            tmp.write(content.encode("utf-8"))
            tmp.flush()
            tmp.close()
            tmp_paths.append(tmp.name)
            sent_files.append(discord.File(tmp.name, filename=safe_name))

        preview_text = files[0][1]
        if len(preview_text) > 800:
            preview_text = preview_text[:800] + "\n\n... (truncated)"
        embed = discord.Embed(
            title="Autocode — Hasil Generate",
            description=f"Bahasa: **{language}**\nDeskripsi: {description[:150]}",
            color=discord.Color.red()
        )

        embed.add_field(name="File Terkirim", value=", ".join(f[0] for f in files), inline=False)
        embed.add_field(name="Preview (potongan)", value=f"```{language_lower}\n{preview_text}\n```", inline=False)
        await interaction.followup.send(embed=embed, files=sent_files)
    except:
        print("autocode send error:", e)
        return await interaction.followup.send("Gagal mengirim file ke Discord.")
    
    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except:
                pass

   

# AI
# chatbot AI
@bot.tree.command(name = "prompt", description = "Ngobrol dengan AI")
@app_commands.describe(pesan = "Apa yang ingin dibicarakan?")
async def chatbot(interaction: discord.Interaction, pesan: str):
    await interaction.response.defer()

    

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/llama-3-8b-instruct", 
        "messages": [
            {"role": "system", "content": "Kamu adalah asisten AI bernama N-library. kamu akan ngobrol menggunakan bahasa indonesia."},
            {"role": "user", "content": pesan}
        ]
    }

    try:
        resp = requests.post(url, json = payload, headers=headers, timeout = 30)
        data = resp.json()
        hasil = data["choices"][0]["message"]["content"]
    except Exception as e:
        return await interaction.followup.send("Gagal memuat API")
    
    await interaction.followup.send(f"**N-LIBRARY:**\n{hasil}")

bot.run(TOKEN)