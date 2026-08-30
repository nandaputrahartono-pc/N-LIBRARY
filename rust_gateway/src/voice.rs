use songbird::events::{Event, EventContext, EventHandler};
use songbird::model::payload::{Speaking};
use std::sync::Arc;
use std::collections::HashMap;
use tokio::sync::Mutex;
use std::time::{Instant, Duration};
use async_trait::async_trait;
use serenity::all::UserId;
use hound::{WavSpec, WavWriter, SampleFormat};
use reqwest::multipart;
use std::io::Cursor;

pub struct UserAudio {
    pub user_id: Option<UserId>,
    pub pcm_data: Vec<i16>,
    pub last_spoke: Instant,
}

#[derive(Clone)]
pub struct Receiver {
    pub guild_id: serenity::all::GuildId,
    pub known_ssrcs: Arc<Mutex<HashMap<u32, UserId>>>,
    pub audio_buffers: Arc<Mutex<HashMap<u32, UserAudio>>>,
    pub reqwest_client: reqwest::Client,
    pub songbird_manager: Arc<songbird::Songbird>,
}

impl Receiver {
    pub fn new(
        guild_id: serenity::all::GuildId,
        songbird_manager: Arc<songbird::Songbird>,
    ) -> Self {
        Self {
            guild_id,
            known_ssrcs: Arc::new(Mutex::new(HashMap::new())),
            audio_buffers: Arc::new(Mutex::new(HashMap::new())),
            reqwest_client: reqwest::Client::new(),
            songbird_manager,
        }
    }
}

#[async_trait]
impl EventHandler for Receiver {
    async fn act(&self, ctx: &EventContext<'_>) -> Option<Event> {
        match ctx {
            EventContext::SpeakingStateUpdate(Speaking {
                speaking: _,
                ssrc,
                user_id,
                ..
            }) => {
                if let Some(uid) = user_id {
                    let mut ssrcs = self.known_ssrcs.lock().await;
                    ssrcs.insert(*ssrc, UserId::new(uid.0));
                }
            }
            EventContext::VoiceTick(tick) => {
                let mut buffers = self.audio_buffers.lock().await;
                let ssrcs = self.known_ssrcs.lock().await;

                // 1. Kumpulkan audio
                for (ssrc, data) in &tick.speaking {
                    if let Some(decoded_voice) = data.decoded_voice.as_ref() {
                        if decoded_voice.is_empty() {
                            continue;
                        }

                        let user_id = ssrcs.get(ssrc).copied();
                        
                        let entry = buffers.entry(*ssrc).or_insert_with(|| UserAudio {
                            user_id,
                            pcm_data: Vec::new(),
                            last_spoke: Instant::now(),
                        });
                        
                        entry.pcm_data.extend_from_slice(decoded_voice);
                        entry.last_spoke = Instant::now();
                    }
                }

                // 2. Deteksi silence
                let now = Instant::now();
                let silence_threshold = Duration::from_millis(1500);
                
                let mut finished_ssrcs = Vec::new();
                for (ssrc, audio) in buffers.iter() {
                    if now.duration_since(audio.last_spoke) > silence_threshold && !audio.pcm_data.is_empty() {
                        finished_ssrcs.push(*ssrc);
                    }
                }

                // 3. Proses (Kirim ke Python)
                for ssrc in finished_ssrcs {
                    if let Some(audio) = buffers.remove(&ssrc) {
                        let uid = audio.user_id;
                        let pcm = audio.pcm_data;
                        let client = self.reqwest_client.clone();
                        let manager = self.songbird_manager.clone();
                        let guild_id = self.guild_id;

                        if let Some(user_id) = uid {
                            tokio::spawn(async move {
                                process_and_send_audio(guild_id, user_id, pcm, client, manager).await;
                            });
                        }
                    }
                }
            }
            _ => {}
        }
        None
    }
}

async fn process_and_send_audio(
    guild_id: serenity::all::GuildId,
    user_id: UserId,
    pcm_data: Vec<i16>,
    client: reqwest::Client,
    manager: Arc<songbird::Songbird>,
) {
    if pcm_data.len() < 48000 {
        return;
    }

    println!("🎙️ Memproses rekaman dari {}...", user_id);

    let spec = WavSpec {
        channels: 2,
        sample_rate: 48000,
        bits_per_sample: 16,
        sample_format: SampleFormat::Int,
    };
    
    let mut cursor = Cursor::new(Vec::new());
    {
        let mut writer = WavWriter::new(&mut cursor, spec).unwrap();
        for sample in pcm_data {
            writer.write_sample(sample).unwrap();
        }
        writer.finalize().unwrap();
    }
    
    let wav_bytes = cursor.into_inner();

    let file_part = multipart::Part::bytes(wav_bytes)
        .file_name("audio.wav")
        .mime_str("audio/wav")
        .unwrap();

    let form = multipart::Form::new()
        .part("file", file_part)
        .text("user_id", user_id.get().to_string())
        .text("user_name", "UserVoice") 
        .text("channel_name", "VoiceChannel")
        .text("participant_count", "2"); 

    match client.post("http://localhost:8000/api/voice_chat")
        .multipart(form)
        .send()
        .await 
    {
        Ok(res) => {
            if res.status().is_success() {
                if let Ok(audio_bytes) = res.bytes().await {
                    if audio_bytes.len() > 10 {
                        println!("🔊 Memutar balasan dari AI...");
                        
                        if let Some(handler_lock) = manager.get(guild_id) {
                            let mut handler = handler_lock.lock().await;
                            let input = songbird::input::Input::from(audio_bytes.to_vec());
                            handler.play_input(input);
                        }
                    }
                }
            }
        }
        Err(e) => {
            println!("⚠️ Gagal konek ke Python API: {}", e);
        }
    }
}