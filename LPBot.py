import discord
from discord.ext import commands
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json
from dotenv import load_dotenv
import asyncio
import random
import requests
import base64
import certifi
import logging
from PIL import Image
from io import BytesIO

logging.getLogger('discord').setLevel(logging.WARNING)


import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from requests.adapters import HTTPAdapter
from requests.sessions import Session


class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


session = Session()
session.verify = certifi.where()
session.mount("https://", TLSAdapter())


# === LOAD ENV ===
load_dotenv()

PERMISSIONS_FILE = "permissions.json"

try:
    with open(PERMISSIONS_FILE, "r") as f:
        permissions = json.load(f)
    print(f"[DEBUG] Loaded permissions: {json.dumps(permissions, indent=2)}")
except Exception as e:
    print(f"[ERROR] Could not load permissions: {e}")
    permissions = {}



# === CONFIG ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ART_SETTING_FILE = "art_setting.json"

# === INTENTS ===
intents = discord.Intents.default()
intents.message_content = True

# === BOT CONFIG ===
bot = commands.Bot(command_prefix="!", intents=intents)

# === SPOTIFY AUTH ===
# scope = "playlist-modify-public playlist-modify-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope="ugc-image-upload playlist-modify-public playlist-modify-private"
))

# === TRACKING ===
SUBMISSIONS_FILE = "submissions.json"
PLAYLIST_MAP_FILE = "playlist_map.json"
QUOTA_FILE = "quotas.json"
LIMIT_FILE = "limits.json"
MAX_DURATION_MS = 7 * 60 * 1000

if os.path.exists(SUBMISSIONS_FILE):
    with open(SUBMISSIONS_FILE, "r") as f:
        user_submissions = json.load(f)
else:
    user_submissions = {}

try:
    with open(PLAYLIST_MAP_FILE, "r") as f:
        playlist_map = json.load(f)
except Exception as e:
    print(f"[ERROR] Could not load playlist_map.json: {e}")
    playlist_map = {}


if os.path.exists(QUOTA_FILE):
    with open(QUOTA_FILE, "r") as f:
        quotas = json.load(f)
else:
    quotas = {}

if os.path.exists(LIMIT_FILE):
    with open(LIMIT_FILE, "r") as f:
        limits = json.load(f)
else:
    limits = {}

if os.path.exists(ART_SETTING_FILE):
    with open(ART_SETTING_FILE, "r") as f:
        art_settings = json.load(f)
else:
    art_settings = {}

# === AI PROMPT GENERATION ===
def generate_prompt():
    adjectives = ["ancient", "neon", "frozen", "haunted", "ethereal", "molten",
                  "gilded", "grim", "sacred", "rusted", "mournful", "vile",
                  "blackened", "forgotten", "celestial", "cybernetic"]
    nouns = ["forest", "cathedral", "goat", "leviathan", "angel", "machine",
             "dungeon", "skeleton", "cult", "ritual", "void", "paladin",
             "oblivion", "specter", "dream", "tomb"]
    actions = ["screaming", "floating", "burning", "shattered", "corrupted",
               "banished", "drifting", "summoning", "mourning", "echoing"]
    themes = ["apocalypse", "moonlight", "hellscape", "sludge", "cosmos",
              "rave", "blood", "winter", "despair", "dissonance"]
    styles = ["black metal album cover", "pixel art", "VHS cover art",
              "oil painting", "dark fantasy concept art", "sci-fi horror artwork"]

    count = random.choice([3, 4, 5])
    parts = []
    if count >= 1:
        parts.append(random.choice(adjectives))
    if count >= 2:
        parts.append(random.choice(nouns))
    if count >= 3:
        parts.append(random.choice(actions))
    if count >= 4:
        parts.append(random.choice(themes))
    if count == 5:
        parts.append(random.choice(styles))

    return " ".join(parts)

# === DALL-E GENERATION ===
def generate_dalle_image(prompt):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024"
    }
    response = requests.post("https://api.openai.com/v1/images/generations", headers=headers, json=data)
    response.raise_for_status()
    image_url = response.json()["data"][0]["url"]
    return image_url


def upload_playlist_cover(playlist_id, image_url):
    try:
        session = Session()
        session.mount("https://", TLSAdapter())

        print(f"[DEBUG] Downloading image from: {image_url}")
        response = session.get(image_url, verify=certifi.where())
        response.raise_for_status()

        # Convert to JPEG
        img = Image.open(BytesIO(response.content)).convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        encoded_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Upload to Spotify
        sp.playlist_upload_cover_image(playlist_id, encoded_image)
        print("[INFO] Playlist cover updated successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to upload playlist cover: {e}")

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    print(f"[DEBUG] Received message from {message.author}: {message.content}")
    await bot.process_commands(message)


@bot.command(name="add")
async def add_to_playlist(ctx, *, song_query: str):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        user_id = str(ctx.author.id)
        if playlist_id not in user_submissions:
            user_submissions[playlist_id] = {}
        if user_id not in user_submissions[playlist_id]:
            user_submissions[playlist_id][user_id] = []

        user_quota = quotas.get(playlist_id, 2)
        if len(user_submissions[playlist_id][user_id]) >= user_quota:
            await ctx.send(f"{ctx.author.mention}, you've hit your submission limit of {user_quota}.")
            return

        # === Check if input is a Spotify track link ===
        if "open.spotify.com/track" in song_query:
            track_id = song_query.split("track/")[-1].split("?")[0]
            track = sp.track(track_id)
        else:
            # === Parse song, artist, optional album ===
            parts = [part.strip() for part in song_query.split('-')]
            if len(parts) < 2:
                await ctx.send("Please format as: song - artist [ - album ] or provide a Spotify track link")
                return

            song, artist = parts[0], parts[1]
            album = parts[2] if len(parts) > 2 else None

            q = f"track:{song} artist:{artist}"
            if album:
                q += f" album:{album}"

            results = sp.search(q=q, type='track', limit=1)
            if not results['tracks']['items']:
                await ctx.send(f"Couldn't find: {song} by {artist}" + (f" on album {album}" if album else ""))
                return
            track = results['tracks']['items'][0]
            track_id = track['id']

        duration = track['duration_ms']

        # === Check for duplicates ===
        existing = [tid for all_t in user_submissions[playlist_id].values() for tid in all_t]
        if track_id in existing:
            await ctx.send("That track has already been submitted to this playlist.")
            return

        track_limit = limits.get(playlist_id, MAX_DURATION_MS)
        if duration > track_limit:
            await ctx.send(f"Track too long (limit is {track_limit // 60000} minutes).")
            return

        sp.playlist_add_items(playlist_id, [track_id])
        user_submissions[playlist_id][user_id].append(track_id)

        with open(SUBMISSIONS_FILE, "w") as f:
            json.dump(user_submissions, f)

        embed = discord.Embed(
    title=track['name'],
    description=f"by {track['artists'][0]['name']}\nAlbum: {track['album']['name']}",
    url=track['external_urls']['spotify']
)

        embed.set_thumbnail(url=track['album']['images'][0]['url'])
        await ctx.send("Track added:", embed=embed)

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="link")
async def playlist_link(ctx):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        await ctx.send(f"Here's the playlist for this channel: {playlist_url}")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="playlist")
async def create_playlist(ctx, action: str, *, args: str):
    try:
        if action.lower() != "add" or " to " not in args:
            await ctx.send("Format: !playlist add <Playlist Name> to <Channel Name>")
            return

        playlist_name, channel_name = args.split(" to ", 1)
        user_id = sp.current_user()["id"]
        new_playlist = sp.user_playlist_create(user_id, playlist_name, public=True)
        playlist_id = new_playlist['id']

        playlist_map[channel_name] = playlist_id
        with open(PLAYLIST_MAP_FILE, "w") as f:
            json.dump(playlist_map, f)

        await ctx.send(f"Playlist '{playlist_name}' linked to channel '{channel_name}'!")

        # === 🧠 Auto-generate and apply art if enabled ===
        gid = str(ctx.guild.id)
        cid = str(ctx.channel.id)
        if art_settings.get(gid, {}).get(cid, False):
            prompt = generate_prompt()
            try:
                image_url = generate_dalle_image(prompt)
                upload_playlist_cover(playlist_id, image_url)
                await ctx.send(f"🖼️ AI-generated cover added using prompt: `{prompt}`")
            except Exception as art_error:
                await ctx.send(f"⚠️ Failed to generate cover art: {art_error}")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")


@bot.command(name="art")
async def toggle_art(ctx, setting: str):
    if not is_organizer(ctx.guild.id, ctx.author.id):
        await ctx.send("❌ You do not have permission to toggle art settings.")
        return

    gid = str(ctx.guild.id)
    cid = str(ctx.channel.id)
    if gid not in art_settings:
        art_settings[gid] = {}

    if setting.lower() == "on":
        art_settings[gid][cid] = True
        await ctx.send("🎨 AI playlist artwork is now ON for this channel.")
    elif setting.lower() == "off":
        art_settings[gid][cid] = False
        await ctx.send("🛑 AI playlist artwork is now OFF for this channel.")
    else:
        await ctx.send("Usage: `!art on` or `!art off`")
        return

    with open(ART_SETTING_FILE, "w") as f:
        json.dump(art_settings, f)

@bot.command(name="refreshart")
async def refresh_art(ctx):
    gid = str(ctx.guild.id)
    cid = str(ctx.channel.id)

    if not is_organizer(gid, ctx.author.id):
        await ctx.send("You do not have permission to refresh playlist art.")
        return

    if not art_settings.get(gid, {}).get(cid, False):
        await ctx.send("Art is not enabled for this channel.")
        return

    playlist_id = playlist_map.get(ctx.channel.name)
    if not playlist_id:
        await ctx.send("No playlist is linked to this channel.")
        return

    try:
        prompt = generate_prompt()
        image_url = generate_dalle_image(prompt)
        upload_playlist_cover(playlist_id, image_url)
        await ctx.send(f"🎨 Playlist art refreshed with prompt: `{prompt}`")
    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send("⚠️ Failed to refresh playlist art.")


@bot.command(name="status")
async def status(ctx):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        playlist = sp.playlist_items(playlist_id, limit=50)
        track_info = {}
        for user_id, tracks in user_submissions.get(playlist_id, {}).items():
            for tid in tracks:
                track_info.setdefault(tid, []).append(user_id)

        message = "**Playlist Submissions:**\n"
        for item in playlist['items']:
            track = item['track']
            users = track_info.get(track['id'], [])
            user_mentions = ", ".join(f"<@{uid}>" for uid in users)
            message += f"{track['name']} by {track['artists'][0]['name']} - Submitted by {user_mentions}\n"

        await ctx.send(message)

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="quota")
async def set_quota(ctx, quota: int):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        quotas[playlist_id] = quota
        with open(QUOTA_FILE, "w") as f:
            json.dump(quotas, f)

        await ctx.send(f"Quota set to {quota} track(s) per user for this playlist.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="limit")
async def set_limit(ctx, minutes: int):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        limits[playlist_id] = minutes * 60000
        with open(LIMIT_FILE, "w") as f:
            json.dump(limits, f)

        await ctx.send(f"Track duration limit set to {minutes} minutes.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="reset")
async def reset_submissions(ctx):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        user_submissions[playlist_id] = {}
        with open(SUBMISSIONS_FILE, "w") as f:
            json.dump(user_submissions, f)

        await ctx.send("Submissions reset for this playlist.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="remove")
async def remove_track(ctx, *, query: str):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        user_id = str(ctx.author.id)
        if playlist_id not in user_submissions or user_id not in user_submissions[playlist_id]:
            await ctx.send("You have not submitted any tracks.")
            return

        submitted_ids = set(user_submissions[playlist_id][user_id])
        playlist_items = sp.playlist_items(playlist_id, limit=100)["items"]

        for item in playlist_items:
            track = item["track"]
            track_id = track["id"]
            full_string = f"{track['name']} - {track['artists'][0]['name']}".lower()

            if track_id in submitted_ids and query.lower() in full_string:
                sp.playlist_remove_all_occurrences_of_items(playlist_id, [track_id])
                user_submissions[playlist_id][user_id].remove(track_id)

                with open(SUBMISSIONS_FILE, "w") as f:
                    json.dump(user_submissions, f)

                await ctx.send(f"Removed: **{track['name']}** by {track['artists'][0]['name']}")
                return

        await ctx.send("Could not find a matching track in your submissions.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")



@bot.command(name="leaderboard")
async def leaderboard(ctx):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(channel_name)
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        counts = {}
        for user_id, tracks in user_submissions.get(playlist_id, {}).items():
            counts[user_id] = len(tracks)

        sorted_leaderboard = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        message = "**Submission Leaderboard:**\n"
        for user_id, count in sorted_leaderboard:
            message += f"<@{user_id}> - {count} track(s)\n"

        await ctx.send(message)

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

# === PERMISSION CHECKS ===
def is_organizer(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)
    return permissions.get(gid, {}).get("organizers", []) and uid in permissions[gid]["organizers"]


def is_user(user_id):
    return str(user_id) in permissions.get("users", []) or is_organizer(user_id)

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")
    for guild in bot.guilds:
        gid = str(guild.id)

        # Ensure the guild exists in the permissions dict
        if gid not in permissions:
            permissions[gid] = {"organizers": [], "users": []}

        invites = []
        inviter = None

        try:
            invites = await guild.invites()
            if invites:
                inviter = invites[0].inviter
        except discord.Forbidden:
            print(f"[ERROR] Could not fetch invites for {guild.name}")

        # 🔒 ONLY reference uid inside this block
        if inviter:
            uid = str(inviter.id)
            if uid not in permissions[gid]["organizers"]:
                permissions[gid]["organizers"].append(uid)
                print(f"[INFO] Added {inviter} as organizer for {guild.name}")

    # Optional: save the updated permissions if needed
    with open(PERMISSIONS_FILE, "w") as f:
        json.dump(permissions, f)


@bot.command(name="user")
async def add_user_permission(ctx, member: discord.Member):
    if not is_organizer(ctx.guild.id, ctx.author.id):
        await ctx.send("You do not have permission to assign roles.")
        return

    uid = str(member.id)
    gid = str(ctx.guild.id)

    if gid not in permissions:
        permissions[gid] = {"organizers": [], "users": []}

    if uid not in permissions[gid]["users"]:
        permissions[gid]["users"].append(uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f)

    await ctx.send(f"✅ User `{member.display_name}` granted user permissions.")


@bot.command(name="organizer")
async def add_organizer_permission(ctx, member: discord.Member):
    if not is_organizer(ctx.guild.id, ctx.author.id):
        await ctx.send("You do not have permission to assign organizer roles.")
        return

    uid = str(member.id)
    gid = str(ctx.guild.id)

    if gid not in permissions:
        permissions[gid] = {"organizers": [], "users": []}

    if uid not in permissions[gid]["organizers"]:
        permissions[gid]["organizers"].append(uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f)

    await ctx.send(f"👑 User `{member.display_name}` granted organizer permissions.")

@bot.command(name="whoami")
async def who_am_i(ctx):
    uid = str(ctx.author.id)
    gid = str(ctx.guild.id)

    role = "No permissions"
    if gid in permissions:
        if uid in permissions[gid]["organizers"]:
            role = "Organizer"
        elif uid in permissions[gid]["users"]:
            role = "User"

    await ctx.send(f"You are: {role}")



@bot.command(name="countdown")
async def countdown(ctx, threshold: int = 3):
    message = await ctx.send("🎵 React to this message to start the listening party countdown!")
    await message.add_reaction("⏯️")

    def check(reaction, user):
        return (
            reaction.message.id == message.id
            and str(reaction.emoji) == "⏯️"
            and not user.bot
        )

    reacted_users = set()
    try:
        while True:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
            reacted_users.add(user.id)
            if len(reacted_users) >= threshold:
                break

        for i in range(5, 0, -1):
            await ctx.send(str(i))
            await asyncio.sleep(1)
        await ctx.send("▶️ GO!")

    except asyncio.TimeoutError:
        await ctx.send("Countdown cancelled. Not enough reactions in time.")

@bot.command(name="lphelp")
async def lphelp_command(ctx):
    help_text = (
        "**🎵 Playlist Management**\n"
        "`!playlist add <name> to <#channel>` – Create & assign playlist to a channel\n"
        "`!link` – Get the Spotify link for the current channel\n"
        "`!reset` – Reset the playlist mapping for this channel\n\n"
        
        "**➕ Adding Songs**\n"
        "`!add <song> - <artist>`\n"
        "`!add <song> - <artist> - <album>`\n"
        "`!add <Spotify link>` – Add directly by Spotify URL\n\n"
        
        "**🚫 Removing Songs**\n"
        "`!remove <song title>` – Remove your own submission\n\n"
        
        "**📊 Playlist Info & Limits**\n"
        "`!status` – Check playlist size & your submissions\n"
        "`!quota <#>` – Set user submission limit *(organizers only)*\n"
        "`!limit <#>` – Set track length limit in minutes *(organizers only)*\n"
        "`!quota` / `!limit` – View current limits\n\n"
        
        "**📈 Leaderboard**\n"
        "`!leaderboard` – View top contributors\n\n"
        
        "**🖼️ Playlist Art**\n"
        "`!art <prompt>` – Generate AI art for the playlist\n"
        "`!refreshart` – Manually re-apply latest art to playlist\n\n"
        
        "**🕵️ Permissions**\n"
        "`!user @name` – Grant user permission\n"
        "`!organizer @name` – Grant organizer permission\n"
        "`!whoami` – Check your permission level\n\n"
        
        "**⏱️ Countdown Mode**\n"
        "`!countdown [#]` – Start a group vote to play the playlist"
    )
    await ctx.send(help_text)


bot.run(DISCORD_TOKEN)
