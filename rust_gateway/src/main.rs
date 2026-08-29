use axum::{
    extract::State,
    routing::post,
    Json, Router,
};
use poise::serenity_prelude as serenity;
use reqwest::Client as HttpClient;
use serde::{Deserialize, Serialize};
use std::process::{Child, Command};
use std::sync::Arc;
use std::collections::HashMap;

// ============================================================
// Python Brain Process Manager
// ============================================================

struct PythonBrain {
    process: Child,
}

impl PythonBrain {
    fn spawn(project_root: &std::path::Path) -> Result<Self, Box<dyn std::error::Error>> {
        let brain_dir = project_root.join("python_brain");
        let venv_python = brain_dir.join("venv").join("Scripts").join("python.exe");

        let python_exe = if venv_python.exists() {
            venv_python
        } else {
            std::path::PathBuf::from("python")
        };

        println!("🐍 Menjalankan Python Brain...");
        let process = Command::new(&python_exe)
            .args(["-m", "uvicorn", "app.main:app", "--port", "8000"])
            .current_dir(&brain_dir)
            .spawn()
            .map_err(|e| format!("Gagal menjalankan Python Brain: {}", e))?;

        Ok(PythonBrain { process })
    }
}

impl Drop for PythonBrain {
    fn drop(&mut self) {
        let _ = self.process.kill();
        let _ = self.process.wait();
        println!("🐍 Python Brain sudah dimatikan.");
    }
}

async fn wait_for_brain(client: &HttpClient) {
    println!("⏳ Menunggu Python Brain siap...");
    for _ in 1..=30 {
        if let Ok(resp) = client.get("http://localhost:8000/health").send().await {
            if resp.status().is_success() {
                println!("✅ Python Brain sudah siap!");
                return;
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    }
}

// ============================================================
// Data & Types
// ============================================================

struct Data {
    http_client: HttpClient,
}

type Error = Box<dyn std::error::Error + Send + Sync>;
type Context<'a> = poise::Context<'a, Data, Error>;

#[derive(Serialize)]
struct ServerState {
    guild_id: String,
    server_name: String,
    is_admin: bool,
    text_channels: Vec<String>,
    voice_channels: Vec<String>,
    activities: HashMap<String, String>,
    recent_history: Vec<String>,
}

#[derive(Serialize)]
struct ChatRequest {
    message: String,
    user_name: String,
    channel_name: String,
    server_state: Option<ServerState>,
}

#[derive(Deserialize)]
struct ChatResponse {
    reply: String,
}

// ============================================================
// Internal API (Axum)
// ============================================================

#[derive(Clone)]
struct AppState {
    http: Arc<serenity::Http>,
    cache: Arc<serenity::Cache>,
}

#[derive(Deserialize)]
struct ManageRoleRequest {
    guild_id: String,
    user_name: String,
    action: String, // "add" | "remove"
    role_name: String,
}

#[derive(Serialize)]
struct ApiResponse {
    success: bool,
    error: Option<String>,
}

async fn manage_role_handler(
    State(state): State<AppState>,
    Json(payload): Json<ManageRoleRequest>,
) -> Json<ApiResponse> {
    let guild_id = match payload.guild_id.parse::<u64>() {
        Ok(id) => serenity::GuildId::new(id),
        Err(_) => return Json(ApiResponse { success: false, error: Some("Invalid Guild ID".into()) }),
    };

    // 1. Cari Role ID berdasarkan nama (dalam block agar CacheRef langsung di-drop)
    let role_id = {
        let guild = match state.cache.guild(guild_id) {
            Some(g) => g,
            None => return Json(ApiResponse { success: false, error: Some("Guild not found in cache".into()) }),
        };
        guild.roles.values()
            .find(|r| r.name.to_lowercase() == payload.role_name.to_lowercase())
            .map(|r| r.id)
    };

    let role_id = match role_id {
        Some(id) => id,
        None => return Json(ApiResponse { success: false, error: Some(format!("Role '{}' tidak ditemukan", payload.role_name)) }),
    };

    // 2. Cari User ID berdasarkan nama (Sub-string matching yang lebih robust)
    let mut member_id = None;
    if let Ok(members) = guild_id.members(&state.http, None, None).await {
         let query = payload.user_name.to_lowercase();
         for m in members {
             let name = m.user.name.to_lowercase();
             let global = m.user.global_name.as_ref().map(|n| n.to_lowercase()).unwrap_or_default();
             let nick = m.nick.as_ref().map(|n| n.to_lowercase()).unwrap_or_default();

             if name.contains(&query) || global.contains(&query) || nick.contains(&query) {
                 member_id = Some(m.user.id);
                 break;
             }
         }
    }

    let user_id = match member_id {
        Some(id) => id,
        None => return Json(ApiResponse { success: false, error: Some(format!("User '{}' tidak ditemukan di server", payload.user_name)) }),
    };

    // 3. Eksekusi tambah atau hapus role via HTTP
    if payload.action == "remove" {
        match state.http.remove_member_role(guild_id, user_id, role_id, Some("AI diinstruksikan oleh Admin")).await {
            Ok(_) => Json(ApiResponse { success: true, error: None }),
            Err(e) => Json(ApiResponse { success: false, error: Some(format!("Discord API Error: {}", e)) }),
        }
    } else {
        match state.http.add_member_role(guild_id, user_id, role_id, Some("AI diinstruksikan oleh Admin")).await {
            Ok(_) => Json(ApiResponse { success: true, error: None }),
            Err(e) => Json(ApiResponse { success: false, error: Some(format!("Discord API Error (bot mungkin gak punya izin Manage Roles, atau posisi role bot lebih rendah): {}", e)) }),
        }
    }
}

// ============================================================
// Slash Commands
// ============================================================

#[poise::command(slash_command)]
async fn ping(ctx: Context<'_>) -> Result<(), Error> {
    ctx.say("Pong! 🏓").await?;
    Ok(())
}

// ============================================================
// Event Handler
// ============================================================

async fn event_handler(
    ctx: &serenity::Context,
    event: &serenity::FullEvent,
    _framework: poise::FrameworkContext<'_, Data, Error>,
    data: &Data,
) -> Result<(), Error> {
    if let serenity::FullEvent::Message { new_message: msg } = event {
        if msg.author.bot { return Ok(()); }

        let bot_id = ctx.cache.current_user().id;
        if !msg.mentions_user_id(bot_id) { return Ok(()); }

        let mut clean_message = msg
            .content
            .replace(&format!("<@{}>", bot_id), "")
            .replace(&format!("<@!{}>", bot_id), "")
            .trim()
            .to_string();

        for user in &msg.mentions {
            let name = user.global_name.as_ref().unwrap_or(&user.name);
            clean_message = clean_message.replace(&format!("<@{}>", user.id), &format!("@{}", name));
            clean_message = clean_message.replace(&format!("<@!{}>", user.id), &format!("@{}", name));
        }

        if clean_message.is_empty() {
            msg.reply(ctx, "Halo! Mau ngobrol apa nih? Tag aku terus kasih pesan ya 😄").await?;
            return Ok(());
        }

        let _ = ctx.http.broadcast_typing(msg.channel_id).await;

        let user_name = msg.author.global_name.clone().unwrap_or(msg.author.name.clone());
        let channel_name = msg.channel_id.name(ctx).await.unwrap_or_else(|_| "unknown".to_string());
        
        // === GATHER CONTEXT ===
        let mut server_state = None;

        if let Some(guild_id) = msg.guild_id {
            let mut is_admin = false;
            let mut server_name = String::new();
            let mut text_channels = Vec::new();
            let mut voice_channels_map: HashMap<serenity::ChannelId, (String, Vec<serenity::UserId>)> = HashMap::new();
            let mut activities = HashMap::new();
            
            let mut presence_data = Vec::new();
            if let Some(guild) = ctx.cache.guild(guild_id) {
                server_name = guild.name.clone();

                if guild.owner_id == msg.author.id {
                    is_admin = true;
                } else if let Some(member) = guild.members.get(&msg.author.id) {
                    if let Some(channel) = guild.channels.get(&msg.channel_id) {
                        if guild.user_permissions_in(channel, member).administrator() {
                            is_admin = true;
                        }
                    }
                }

                for (id, channel) in guild.channels.iter() {
                    match channel.kind {
                        serenity::ChannelType::Text => text_channels.push(format!("#{}", channel.name)),
                        serenity::ChannelType::Voice => { voice_channels_map.insert(*id, (channel.name.clone(), Vec::new())); },
                        _ => {}
                    }
                }

                for (user_id, voice_state) in guild.voice_states.iter() {
                    if let Some(channel_id) = voice_state.channel_id {
                        if let Some(vc_info) = voice_channels_map.get_mut(&channel_id) {
                            vc_info.1.push(*user_id);
                        }
                    }
                }

                for (user_id, presence) in guild.presences.iter() {
                    let mut user_activities = Vec::new();
                    for activity in &presence.activities {
                        if activity.kind == serenity::model::gateway::ActivityType::Custom {
                            if let Some(state) = &activity.state {
                                user_activities.push(format!("Status: '{}'", state));
                            }
                        } else {
                            let action = match activity.kind {
                                serenity::model::gateway::ActivityType::Playing => "Main game",
                                serenity::model::gateway::ActivityType::Listening => "Dengerin",
                                serenity::model::gateway::ActivityType::Watching => "Nonton",
                                serenity::model::gateway::ActivityType::Streaming => "Streaming",
                                _ => "Aktivitas",
                            };
                            user_activities.push(format!("{} {}", action, activity.name));
                        }
                    }
                    if !user_activities.is_empty() {
                        presence_data.push((*user_id, user_activities.join(" | ")));
                    }
                }
            } // end of guild cache lock

            // Resolve nama user untuk Activities
            for (user_id, acts_str) in presence_data {
                if let Ok(user) = user_id.to_user(ctx).await {
                    let name = user.global_name.clone().unwrap_or(user.name.clone());
                    activities.insert(name, acts_str);
                }
            }

            let mut formatted_voice_channels = Vec::new();
            for (_, (vc_name, user_ids)) in voice_channels_map {
                if user_ids.is_empty() {
                    formatted_voice_channels.push(format!("🔊 {} (Kosong)", vc_name));
                } else {
                    let mut participants = Vec::new();
                    for uid in user_ids {
                        if let Ok(user) = uid.to_user(ctx).await {
                            participants.push(user.global_name.clone().unwrap_or(user.name.clone()));
                        }
                    }
                    formatted_voice_channels.push(format!("🔊 {} (Member: {})", vc_name, participants.join(", ")));
                }
            }
            formatted_voice_channels.sort();
            text_channels.sort();

            let mut recent_history = Vec::new();
            if let Ok(messages) = msg.channel_id.messages(ctx, serenity::GetMessages::new().before(msg.id).limit(10)).await {
                for m in messages.iter().rev() {
                    let name = m.author.global_name.clone().unwrap_or(m.author.name.clone());
                    let mut content = m.content.clone();
                    for user in &m.mentions {
                        let mentioned_name = user.global_name.as_ref().unwrap_or(&user.name);
                        content = content.replace(&format!("<@{}>", user.id), &format!("@{}", mentioned_name));
                        content = content.replace(&format!("<@!{}>", user.id), &format!("@{}", mentioned_name));
                    }
                    recent_history.push(format!("{}: {}", name, content));
                }
            }

            server_state = Some(ServerState {
                guild_id: guild_id.get().to_string(),
                server_name,
                is_admin,
                text_channels,
                voice_channels: formatted_voice_channels,
                activities,
                recent_history,
            });
        }

        let request_body = ChatRequest {
            message: clean_message,
            user_name,
            channel_name,
            server_state,
        };

        match data.http_client.post("http://localhost:8000/chat").json(&request_body).send().await {
            Ok(response) => {
                if response.status().is_success() {
                    if let Ok(chat_response) = response.json::<ChatResponse>().await {
                        let reply = if chat_response.reply.len() > 1900 {
                            format!("{}...", &chat_response.reply[..1900])
                        } else {
                            chat_response.reply
                        };
                        let _ = msg.reply(ctx, &reply).await;
                    }
                } else {
                    let _ = msg.reply(ctx, "Otakku lagi lemot nih, coba lagi nanti ya 😵").await;
                }
            }
            Err(_) => {
                let _ = msg.reply(ctx, "🔌 Otak AI-ku lagi offline. Pastikan Python Brain sudah jalan ya!").await;
            }
        }
    }
    Ok(())
}

// ============================================================
// Main
// ============================================================

#[tokio::main]
async fn main() {
    let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf();
    
    dotenvy::from_path(project_root.join(".env")).expect("Gagal membaca file .env!");
    let token = std::env::var("TOKEN_DISCORD1").expect("TOKEN_DISCORD1 tidak ditemukan di file .env!");

    // 1. Start Python Brain
    let _brain = PythonBrain::spawn(&project_root).expect("Gagal menjalankan Python Brain!");
    let http_client = HttpClient::new();
    wait_for_brain(&http_client).await;

    // 2. Setup Serenity (Discord)
    // Butuh PRESENCES, MEMBERS, dan VOICE_STATES untuk membaca aktivitas, nama orang di VC, dan role
    let intents = serenity::GatewayIntents::non_privileged()
        | serenity::GatewayIntents::MESSAGE_CONTENT
        | serenity::GatewayIntents::GUILD_PRESENCES
        | serenity::GatewayIntents::GUILD_MEMBERS
        | serenity::GatewayIntents::GUILD_VOICE_STATES;

    let framework = poise::Framework::builder()
        .options(poise::FrameworkOptions {
            commands: vec![ping()],
            event_handler: |ctx, event, framework, data| {
                Box::pin(event_handler(ctx, event, framework, data))
            },
            ..Default::default()
        })
        .setup(|ctx, _ready, framework| {
            Box::pin(async move {
                poise::builtins::register_globally(ctx, &framework.options().commands).await?;
                println!("🦀 N-LIBRARY Gateway (Rust) sudah online!");
                Ok(Data { http_client })
            })
        })
        .build();

    let mut client = serenity::ClientBuilder::new(&token, intents)
        .framework(framework)
        .await
        .expect("Gagal membuat Discord client");

    // 3. Start Axum Server for Internal API
    let axum_state = AppState {
        http: client.http.clone(),
        cache: client.cache.clone(),
    };

    let app = Router::new()
        .route("/api/role", post(manage_role_handler))
        .with_state(axum_state);

    tokio::spawn(async move {
        let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await.unwrap();
        println!("🚀 Internal API (Axum) running on http://0.0.0.0:8080");
        axum::serve(listener, app).await.unwrap();
    });

    // 4. Start Discord Bot
    println!("🚀 Semua service berjalan! Bot siap digunakan.");
    if let Err(e) = client.start().await {
        eprintln!("[FATAL] Bot gagal start: {:?}", e);
    }
}
