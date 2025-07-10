import discord
from discord.ext import commands, tasks
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
import aiohttp
from PIL import Image
from io import BytesIO
from datetime import datetime, timedelta
import re

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


permissions = {}
if os.path.exists(PERMISSIONS_FILE):
    try:
        with open(PERMISSIONS_FILE, "r") as f:
            permissions = json.load(f)

        # print(f"[DEBUG] Loaded permissions: {json.dumps(permissions, indent=2)}")
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse permissions file: {e}")
        # Optional: back up the corrupted file
        os.rename(PERMISSIONS_FILE, PERMISSIONS_FILE + ".bak")
        print(f"[INFO] Corrupted permissions file backed up.")
else:
    print("[INFO] No permissions file found, starting fresh.")

active_polls = {}  # key = poll name
locks = {}  # {message_id: asyncio.Lock()}


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
intents.presences = True
intents.members = True

# === BOT CONFIG ===
bot = commands.Bot(command_prefix="!", intents=intents)

# === SPOTIFY AUTH ===
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope="ugc-image-upload playlist-modify-public playlist-modify-private"
))

# === TRACKING ===
SUBMISSIONS_FILE = "user_submissions.json"
PLAYLIST_MAP_FILE = "playlist_map.json"
QUOTA_FILE = "submission_quotas.json"
LIMIT_FILE = "duration_limits.json"
MAX_DURATION_MS = 7 * 60 * 1000

if os.path.exists(SUBMISSIONS_FILE):
    with open(SUBMISSIONS_FILE, "r") as f:
        user_submissions = json.load(f)

else: 
    user_submissions = {}

print(f"[DEBUG] Loaded submissions: {json.dumps(user_submissions, indent=2)}")

try:
    with open(PLAYLIST_MAP_FILE, "r") as f:
        playlist_map = json.load(f)
except Exception as e:
    print(f"[ERROR] Could not load playlist_map.json: {e}")
    playlist_map = {}

if os.path.exists(QUOTA_FILE):
    with open(QUOTA_FILE, "r") as f:
        submission_quotas = json.load(f)
else:
    submission_quotas = {}

if os.path.exists(LIMIT_FILE):
    with open(LIMIT_FILE, "r") as f:
        duration_limits = json.load(f)
else:
    duration_limits = {}

if os.path.exists(ART_SETTING_FILE):
    with open(ART_SETTING_FILE, "r") as f:
        art_settings = json.load(f)
else:
    art_settings = {}


# Role to allowed commands mapping
ROLE_PERMISSIONS = {
    "administrator": {
        "add", "remove", "quota", "limit", "status", "link", "leaderboard", "countdown",
        "user", "organizer", "administrator", "whoami", "lphelp",
        "art", "artchannel", "refreshart", "reset", "playlist"
    },
    "organizer": {
        "add", "remove", "quota", "limit", "status", "link", "leaderboard", "countdown",
        "user", "whoami", "lphelp"
    },
    "user": {
        "add", "remove", "status", "leaderboard", "link", "whoami", "lphelp"
    }
}

def ensure_permissions_structure(gid):
    if gid not in permissions:
        permissions[gid] = {
            "administrators": [],
            "organizers": [],
            "users": [],
        }
    else:
        for key in ["administrators", "organizers", "users"]:
            if key not in permissions[gid]:
                permissions[gid][key] = []


def get_user_role(guild_id, user_id):
    user_id = str(user_id)
    guild_id = str(guild_id)
    guild_perms = permissions.get(guild_id, {})

    if user_id in guild_perms.get("administrators", []):
        return "administrator"
    elif user_id in guild_perms.get("organizers", []):
        return "organizer"
    elif user_id in guild_perms.get("users", []):
        return "user"
    else:
        return None

def has_permission(command_name, user_role):
    allowed = ROLE_PERMISSIONS.get(user_role, set())
    return command_name in allowed or user_role == "administrator"

def get_permission_level(guild_id, user_id):
    guild_perms = permissions.get(str(guild_id), {})
    user_id = str(user_id)

    if user_id in guild_perms.get("administrators", []):
        return "Administrator"
    elif user_id in guild_perms.get("organizers", []):
        return "Organizer"
    elif user_id in guild_perms.get("users", []):
        return "User"
    else:
        return "No permissions"

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

def get_all_playlist_tracks(sp, playlist_id):
    all_tracks = []
    offset = 0
    limit = 100

    while True:
        response = sp.playlist_items(playlist_id, offset=offset, limit=limit)
        items = response.get("items", [])
        if not items:
            break
        all_tracks.extend(items)
        offset += len(items)

    return all_tracks


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Poll reply logic
    if message.reference and message.reference.message_id:
        for poll_key, poll in active_polls.items():
            if poll["status"] == "collecting" and message.reference.message_id == poll["message_id"]:
                user_id = str(message.author.id)

                # Make sure this is a reply to THIS poll only
                if str(message.channel.id) != poll["channel_id"]:
                    continue

                # Initialize user's submission list
                if user_id not in poll["submissions"]:
                    poll["submissions"][user_id] = []

                if len(poll["submissions"][user_id]) >= poll["submission_limit"]:
                    await message.channel.send("⚠️ You've reached your submission limit for this poll.", delete_after=5)
                else:
                    poll["submissions"][user_id].append(message.content)
                    print(f"[POLL] {message.author} submitted to '{poll_key}': {message.content}")
                break  # stop once matched correctly

        # Debug embed structure if replying to an fmbot message
        try:
            replied_msg = await message.channel.fetch_message(message.reference.message_id)
            if replied_msg.embeds:
                embed = replied_msg.embeds[0]
                print("[DEBUG] FMbot Embed JSON:", embed.to_dict())
        except Exception as e:
            print(f"[ERROR] Failed to fetch replied message or embed: {e}")

    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot: return

    msg_id = reaction.message.id
    poll = next((p for p in active_polls.values() if p.get("vote_message_id") == msg_id and p["status"] == "voting"), None)
    if not poll or poll.get("vote_limit") is None:
        return

    # Create/init lock
    if msg_id not in locks:
        locks[msg_id] = asyncio.Lock()

    async with locks[msg_id]:
        votes = user_votes.setdefault(msg_id, {}).setdefault(user.id, [])
        if poll["vote_limit"] == 1:
            # Remove all previous votes atomically
            for e in votes:
                try:
                    await reaction.message.remove_reaction(e, user)
                except:
                    pass
            votes.clear()
            votes.append(reaction.emoji)
        else:
            if reaction.emoji in votes:
                return
            if len(votes) >= poll["vote_limit"]:
                try:
                    await reaction.message.remove_reaction(reaction.emoji, user)
                except:
                    pass
            else:
                votes.append(reaction.emoji)

@bot.event
async def on_reaction_remove(reaction, user):
    message_id = reaction.message.id
    if message_id in user_votes and user.id in user_votes[message_id]:
        if reaction.emoji in user_votes[message_id][user.id]:
            user_votes[message_id][user.id].remove(reaction.emoji)


@bot.command(name="add", aliases=["a"])
async def add_to_playlist(ctx, *, song_query: str = None): # type: ignore
    try:
        gid = str(ctx.guild.id)
        cid = str(ctx.channel.id)
        user_id = str(ctx.author.id)

        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(str(ctx.channel.id))
        # playlist_id = playlist_map.get(channel_name)

        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        # === Ensure structure exists ===
        if gid not in user_submissions:
            user_submissions[gid] = {}
        if playlist_id not in user_submissions[gid]:
            user_submissions[gid][playlist_id] = {}
        if user_id not in user_submissions[gid][playlist_id]:
            user_submissions[gid][playlist_id][user_id] = []

        # === Quota lookup ===
        user_quota = submission_quotas.get(gid, {}).get(cid, 2)
        user_tracks = user_submissions[gid][playlist_id][user_id]

        if len(user_tracks) >= user_quota:
            await ctx.send(f"{ctx.author.mention}, you've hit your submission limit of {user_quota}.")
            return

        # === Try FMbot reply parsing first ===
        if not song_query and ctx.message.reference:
            try:
                replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if replied_msg.embeds:
                    embed = replied_msg.embeds[0]
                    desc = embed.description or ""

                    track_match = re.search(r"\[([^\]]+)\]\(", desc)
                    artist_match = re.search(r"\*\*(.*?)\*\*", desc)
                    if track_match and artist_match:
                        title = track_match.group(1).strip()
                        artist = artist_match.group(1).strip()
                        song_query = f"{title} - {artist}"
                        print(f"[DEBUG] Pulled from fmbot reply: {song_query}")
            except Exception as e:
                print(f"[ERROR] Failed to parse fmbot reply: {e}")

        # === Try Spotify presence as a fallback ===
        if not song_query:
            print(f"[DEBUG] Activities: {ctx.author.activities}")
            activity = discord.utils.find(lambda a: isinstance(a, discord.Spotify), ctx.author.activities)
            if activity:
                song_query = f"{activity.title} - {activity.artist}"
                print(f"[DEBUG] Using Spotify presence: {song_query}")

        if not song_query:
            await ctx.send("❌ No song info found. Provide a search query, reply to a .fmbot message, or make sure you're visible on Spotify.")
            return

        # === Track Lookup ===
        if "open.spotify.com/track" in song_query:
            track_id = song_query.split("track/")[-1].split("?")[0]
            track = sp.track(track_id)
        else:
            parts = [part.strip() for part in song_query.split('-')]
            if len(parts) < 2:
                await ctx.send("Please format as: song - artist [ - album ] or provide a Spotify link")
                return

            song, artist = parts[0], parts[1]
            album = parts[2] if len(parts) > 2 else None
            q = f"track:{song} artist:{artist}" + (f" album:{album}" if album else "")
            results = sp.search(q=q, type='track', limit=1)

            if not results['tracks']['items']: # type: ignore
                await ctx.send(f"Couldn't find: {song} by {artist}" + (f" on album {album}" if album else ""))
                return

            track = results['tracks']['items'][0] # type: ignore
            track_id = track['id']

        # === Duration Limit ===
        duration = track['duration_ms'] # type: ignore

        limit_minutes = duration_limits.get(gid, {}).get(cid, MAX_DURATION_MS // 60000)
        track_limit = limit_minutes * 60000

        if duration > track_limit:
            await ctx.send(f"Track too long (limit is {limit_minutes} minutes).")
            return

        # === Check for duplicates ===
        all_submitted = [tid for u in user_submissions[gid][playlist_id].values() for tid in u]
        if track_id in all_submitted:
            await ctx.send("This track has already been submitted.")
            return

        # === Add and persist ===
        sp.playlist_add_items(playlist_id, [track_id])
        user_tracks.append(track_id)

        with open(SUBMISSIONS_FILE, "w") as f:
            json.dump(user_submissions, f)

        embed = discord.Embed(
            title=track['name'], # type: ignore
            description=f"by {track['artists'][0]['name']}\nAlbum: {track['album']['name']}", # type: ignore
            url=track['external_urls']['spotify'] # type: ignore
        )
        embed.set_thumbnail(url=track['album']['images'][0]['url']) # type: ignore
        await ctx.send("✅ Track added:", embed=embed)

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="link", aliases=["lk"])
async def playlist_link(ctx):
    try:
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(str(ctx.channel.id))
        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        await ctx.send(f"Here's the playlist for this channel: {playlist_url}")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="playlist", aliases=["p"])
async def create_playlist(ctx, action: str, *, args: str):
    try:
        if action.lower() != "add" or " to " not in args:
            await ctx.send("Format: !playlist add <Playlist Name> to <Channel Name>")
            return

        playlist_name, channel_name = args.split(" to ", 1)
        user_id = sp.current_user()["id"] # type: ignore
        new_playlist = sp.user_playlist_create(user_id, playlist_name, public=True)
        playlist_id = new_playlist['id'] # type: ignore

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
    if not is_administrator(ctx.guild.id, ctx.author.id):
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


@bot.command(name="refreshart", aliases=["ra"])
async def refresh_art(ctx, *, custom_prompt: str = None): # type: ignore
    gid = str(ctx.guild.id)
    cid = str(ctx.channel.id)

    if not is_administrator(gid, ctx.author.id):
        await ctx.send("🚫 You do not have permission to refresh playlist art.")
        return

    if not art_settings.get(gid, {}).get(cid, False):
        await ctx.send("🎨 Art is not enabled for this channel.")
        return

    playlist_id = playlist_map.get(str(ctx.channel.id))
    if not playlist_id:
        await ctx.send("⚠️ No playlist is linked to this channel.")
        return

    try:
        prompt = custom_prompt if custom_prompt else generate_prompt()
        print(f"[DEBUG] Using prompt: {prompt}")

        image_url = generate_dalle_image(prompt)
        print(f"[DEBUG] Downloaded image from: {image_url}")
            
        # Clean up prompt to make it safe for filenames
        def sanitize_filename(text):
            return re.sub(r'[^a-zA-Z0-9_-]', '_', text)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        safe_prompt = sanitize_filename(prompt)

        # Get human-readable folder names
        guild_name = sanitize_filename(ctx.guild.name)
        channel_name = sanitize_filename(ctx.channel.name)

        folder_name = f"{guild_name}_{channel_name}"
        local_dir = os.path.join("playlist_art", folder_name)
        os.makedirs(local_dir, exist_ok=True)

        local_filename = os.path.join(local_dir, f"{safe_prompt}_{timestamp}.png")

        # Download the image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    with open(local_filename, 'wb') as f:
                        f.write(await resp.read())
                    print(f"[INFO] Image saved to {local_filename}")
                else:
                    raise Exception(f"Failed to download image: {resp.status}")


        # Reupload to Discord for embedding
        file = discord.File(local_filename, filename="playlist_art.png")
        embed = discord.Embed(title="🖼️ New Playlist Art", description=f"Prompt: `{prompt}`")
        embed.set_image(url="attachment://playlist_art.png")

        upload_playlist_cover(playlist_id, image_url)
        print(f"[INFO] Playlist cover updated successfully.")
        print(f"[DEBUG] Uploaded playlist cover for: {playlist_id}")

        await ctx.send(f"🎨 Playlist art refreshed with prompt: `{prompt}`")

        # Send image to art channel if it's configured
        art_channel_id = permissions.get(gid, {}).get("art_channel")
        if art_channel_id:
            art_channel = bot.get_channel(int(art_channel_id))
            if art_channel:
                embed = discord.Embed(title="🖼️ New Playlist Art", description=f"Prompt: `{prompt}`")
                # embed.set_image(url=image_url)
                await art_channel.send(file=file, embed=embed) # type: ignore
            else:
                print(f"[WARN] Art channel not found: {art_channel_id}")

    except Exception as e:
        print(f"[ERROR] Failed to refresh playlist art: {e}")
        await ctx.send("⚠️ Failed to refresh playlist art.")

@bot.command(name="prompt")
async def generate_ai_prompt(ctx):
    try:
        prompt = generate_prompt()
        await ctx.send(f"🎨 Generated AI prompt: `{prompt}`")
    except Exception as e:
        print(f"[ERROR] Failed to generate prompt: {e}")
        await ctx.send("⚠️ Failed to generate AI prompt.")

@bot.command(name="artchannel")
async def set_art_channel(ctx, *, channel_name: str):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)

    if not is_organizer(gid, uid):
        await ctx.send("You do not have permission to set the art channel.")
        return

    # Find the channel by name
    art_channel = discord.utils.get(ctx.guild.text_channels, name=channel_name)
    if not art_channel:
        await ctx.send(f"⚠️ Channel '{channel_name}' not found.")
        return

    # Ensure safe permissions structure without overwriting
    ensure_permissions_structure(gid)

    permissions[gid]["art_channel"] = str(art_channel.id)

    # Backup existing file (optional but clutch while testing)
    try:
        import shutil
        shutil.copy(PERMISSIONS_FILE, PERMISSIONS_FILE + ".bak")
    except Exception as e:
        print(f"[WARN] Couldn't backup permissions file: {e}")

    # Safe save
    try:

        import traceback

        print(f"[DEBUG] Writing to {PERMISSIONS_FILE} from {ctx.command.name if 'ctx' in locals() else 'unknown'}")
        traceback.print_stack()

        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f, indent=4)
        print("[DEBUG] Permissions saved successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to save permissions: {e}")

    await ctx.send(f"✅ Playlist art will now be posted in #{art_channel.name}")


@bot.command(name="status", aliases=["s"])
async def status(ctx):
    try:
        gid = str(ctx.guild.id)
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(str(ctx.channel.id))


        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        playlist_items = sp.playlist_items(playlist_id, limit=100)["items"]  # type: ignore
        submission_data = user_submissions.get(gid, {}).get(playlist_id, {})

        status_lines = []
        for item in playlist_items:
            track = item["track"]
            track_id = track["id"]
            user_name = "Unknown"

            # Find who submitted the track
            for user_id, tracks in submission_data.items():
                if track_id in tracks:
                    try:
                        member = await ctx.guild.fetch_member(int(user_id))
                        user_name = member.display_name
                    except:
                        user_name = f"👻 Unknown User"
                    break

            status_lines.append(f"{track['name']} by {track['artists'][0]['name']} — submitted by {user_name}")

        if status_lines:
            await ctx.send("**📄 Playlist Submissions:**\n" + "\n".join(status_lines))
        else:
            await ctx.send("📭 No tracks found in the playlist.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")


@bot.command(name="quota", aliases=["q"])
async def set_quota(ctx, quota: int = None): # type: ignore
    gid = str(ctx.guild.id)
    cid = str(ctx.channel.id)
    role = get_user_role(gid, ctx.author.id)

    print(f"[DEBUG] User {ctx.author.id} role in guild {gid}: {role}")

    if not has_permission("quota", role):
        await ctx.send("🚫 You don't have permission to set or view the quota.")
        return

    if quota is None:
        current_quota = submission_quotas.get(gid, {}).get(cid)
        if current_quota is not None:
            await ctx.send(f"📊 Current quota is `{current_quota}` tracks per user.")
        else:
            await ctx.send("📊 No quota is set for this channel.")
        return

    if gid not in submission_quotas:
        submission_quotas[gid] = {}
    submission_quotas[gid][cid] = quota

    with open(QUOTA_FILE, "w") as f:
        json.dump(submission_quotas, f)

    await ctx.send(f"✅ Quota set to `{quota}` track(s) per user for this playlist.")


@bot.command(name="limit", aliases=["l"])
async def set_limit(ctx, minutes: int = None): # type: ignore
    gid = str(ctx.guild.id)
    cid = str(ctx.channel.id)
    role = get_user_role(gid, ctx.author.id)

    if not has_permission("limit", role):
        await ctx.send("🚫 You don't have permission to set the track limit.")
        return

    if minutes is None:
        current_limit = duration_limits.get(gid, {}).get(cid)
        if current_limit:
            await ctx.send(f"⏱️ Current track duration limit is `{current_limit}` minutes.")
        else:
            await ctx.send("⏱️ No duration limit is set for this channel.")
        return

    # Save the new limit
    if gid not in duration_limits:
        duration_limits[gid] = {}
    duration_limits[gid][cid] = minutes

    with open(LIMIT_FILE, "w") as f:
        json.dump(duration_limits, f)

    await ctx.send(f"✅ Track duration limit set to `{minutes}` minutes.")


@bot.command(name="reset")
async def reset_playlist(ctx):
    try:
        gid = str(ctx.guild.id)
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(str(ctx.channel.id))

        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        # Fetch all tracks from the playlist
        tracks = []
        results = sp.playlist_items(playlist_id, limit=100)
        tracks.extend(results["items"]) # type: ignore
        while results["next"]: # type: ignore
            results = sp.next(results)
            tracks.extend(results["items"]) # type: ignore

        # Collect all track IDs
        track_ids = [item["track"]["id"] for item in tracks if item["track"]]

        if not track_ids:
            await ctx.send("Playlist is already empty.")
            return

        # Remove all tracks in chunks of 100 (API limit)
        for i in range(0, len(track_ids), 100):
            chunk = track_ids[i:i+100]
            sp.playlist_remove_all_occurrences_of_items(playlist_id, chunk)

        # Clear submissions in our structure
        if gid in user_submissions and playlist_id in user_submissions[gid]:
            del user_submissions[gid][playlist_id]
            if not user_submissions[gid]:  # cleanup if empty
                del user_submissions[gid]

        with open(SUBMISSIONS_FILE, "w") as f:
            json.dump(user_submissions, f, indent=2)

        await ctx.send("💥 Playlist has been reset. All tracks removed.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")


@bot.command(name="remove", aliases=["r"])
async def remove_track(ctx, *, query: str):
    try:
        gid = str(ctx.guild.id)
        cid = str(ctx.channel.id)
        user_id = str(ctx.author.id)

        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(str(ctx.channel.id))

        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        # New structure check

        playlist_items = get_all_playlist_tracks(sp, playlist_id) # type: ignore
        # print(f"[DEBUG] Guild ID: {gid}")
        # print(f"[DEBUG] Playlist ID: {playlist_id}")
        # print(f"[DEBUG] User ID: {user_id}")
        # print(f"[DEBUG] user_submissions keys: {list(user_submissions.keys())}")
        # print(f"[DEBUG] user_submissions[gid] keys: {list(user_submissions.get(gid, {}).keys())}")
        # print(f"[DEBUG] user_submissions[gid][playlist_id] keys: {list(user_submissions.get(gid, {}).get(playlist_id, {}).keys())}")

        print(user_submissions)

        submitted_ids = set(user_submissions[gid][playlist_id][user_id])

        # print(f"[DEBUG] Submitted IDs: {submitted_ids}")
        # for item in playlist_items:
        #     print(f"[DEBUG] Track in playlist: {item['track']['name']} - {item['track']['id']}")


        if gid not in user_submissions or \
           playlist_id not in user_submissions[gid] or \
           user_id not in user_submissions[gid][playlist_id]:
            await ctx.send("You have not submitted any tracks.")
            return


        for item in playlist_items:
            track = item["track"]
            track_id = track["id"]
            full_string = f"{track['name']} - {track['artists'][0]['name']}".lower()

            if track_id in submitted_ids and query.lower() in full_string:
                sp.playlist_remove_all_occurrences_of_items(playlist_id, [track_id])
                user_submissions[gid][playlist_id][user_id].remove(track_id)

                with open(SUBMISSIONS_FILE, "w") as f:
                    json.dump(user_submissions, f)

                await ctx.send(f"🗑️ Removed: **{track['name']}** by {track['artists'][0]['name']}")
                return

        await ctx.send("Could not find a matching track in your submissions.")

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="leaderboard")
async def leaderboard(ctx):
    try:
        gid = str(ctx.guild.id)
        channel_name = ctx.channel.name
        playlist_id = playlist_map.get(str(ctx.channel.id))

        if not playlist_id:
            await ctx.send("No playlist linked to this channel.")
            return

        submission_data = user_submissions.get(gid, {}).get(playlist_id, {})
        if not submission_data:
            await ctx.send("No submissions yet.")
            return

        leaderboard_data = []

        for user_id, tracks in submission_data.items():
            count = len(tracks)
            try:
                member = await ctx.guild.fetch_member(int(user_id))
                name = member.display_name
            except:
                name = f"👻 Unknown User"
            leaderboard_data.append((name, count))

        # Sort descending by count
        leaderboard_data.sort(key=lambda x: x[1], reverse=True)

        msg_lines = ["**🎧 Submission Leaderboard:**"]
        for i, (name, count) in enumerate(leaderboard_data, 1):
            msg_lines.append(f"{i}. {name} — {count} track{'s' if count != 1 else ''}")

        await ctx.send("\n".join(msg_lines))

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")


def is_user(user_id):
    return str(user_id) in permissions.get("users", []) or is_organizer(user_id) # type: ignore

def is_administrator(gid, uid):
    return str(uid) in permissions.get(str(gid), {}).get("administrators", [])

def is_organizer(gid, uid):
    return str(uid) in permissions.get(str(gid), {}).get("organizers", [])


@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})") # type: ignore
    updated = False

    for guild in bot.guilds:
        gid = str(guild.id)

        # Only update if something was actually added
        before = json.dumps(permissions.get(gid, {}), sort_keys=True)

        ensure_permissions_structure(gid)

        invites = []
        inviter = None

        # Check if changes occurred
        after = json.dumps(permissions.get(gid, {}), sort_keys=True)
        if before != after:
            updated = True

    # Only save if something changed
    if updated:
        try:
            import traceback
            print("[DEBUG] Writing to permissions.json from on_ready()")
            traceback.print_stack()

            with open(PERMISSIONS_FILE, "w") as f:
                json.dump(permissions, f, indent=4)
            print("[DEBUG] Permissions saved after bot ready.")
        except Exception as e:
            print(f"[ERROR] Failed to save permissions: {e}")
    else:
        print("[DEBUG] No changes to permissions. Skipping write.")


@bot.command(name="user")
async def add_user_permission(ctx, member: discord.Member):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    target_uid = str(member.id)

    if not is_organizer(gid, uid) and not is_administrator(gid, uid):
        await ctx.send("You do not have permission to assign roles.")
        return

    # === Safely ensure all roles exist ===
    if gid not in permissions:
        permissions[gid] = {
            "administrators": [],
            "organizers": [],
            "users": []
        }
    else:
        for key in ["administrators", "organizers", "users"]:
            if key not in permissions[gid]:
                permissions[gid][key] = []

    if target_uid not in permissions[gid]["users"]:
        permissions[gid]["users"].append(target_uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f, indent=4)

    await ctx.send(f"✅ User `{member.display_name}` granted user permissions.")

@bot.command(name="organizer")
async def add_organizer_permission(ctx, member: discord.Member):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    target_uid = str(member.id)

    # ✅ Allow both organizers and admins to assign organizer role
    if not is_organizer(gid, uid) and not is_administrator(gid, uid):
        await ctx.send("You do not have permission to assign organizer roles.")
        return

    # ✅ Safely ensure permissions structure
    if gid not in permissions:
        permissions[gid] = {
            "administrators": [],
            "organizers": [],
            "users": []
        }
    else:
        for key in ["administrators", "organizers", "users"]:
            if key not in permissions[gid]:
                permissions[gid][key] = []

    # ✅ Add the user if they’re not already an organizer
    if target_uid not in permissions[gid]["organizers"]:
        permissions[gid]["organizers"].append(target_uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f, indent=4)

    await ctx.send(f"👑 User `{member.display_name}` granted organizer permissions.")

@bot.command(name="administrator")
async def add_administrator_permission(ctx, member: discord.Member):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    target_uid = str(member.id)

    # ✅ Allow both organizers and admins to assign organizer role
    if not is_organizer(gid, uid) and not is_administrator(gid, uid):
        await ctx.send("You do not have permission to assign organizer roles.")
        return

    # ✅ Safely ensure permissions structure
    if gid not in permissions:
        permissions[gid] = {
            "administrators": [],
            "organizers": [],
            "users": []
        }
    else:
        for key in ["administrators", "organizers", "users"]:
            if key not in permissions[gid]:
                permissions[gid][key] = []

    # ✅ Add the user if they’re not already an Admin
    if target_uid not in permissions[gid]["administrators"]:
        permissions[gid]["administrators"].append(target_uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f, indent=4)

    await ctx.send(f"🤖 User `{member.display_name}` granted administrator permissions.")


@bot.command(name="whoami")
async def who_am_i(ctx):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    role = get_permission_level(gid, uid)
    await ctx.send(f"You are: **{role}**")


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

@bot.command(name="wheel")
async def start_wheel(ctx, seconds: int = 60):
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)

    if not (is_organizer(gid, uid) or is_administrator(gid, uid)):
        await ctx.send("🚫 You do not have permission to start the wheel.")
        return

    if seconds < 30:
        await ctx.send("⏳ Timer must be at least 30 seconds to give people a chance.")
        return
    
    if seconds > 180:
        await ctx.send("🕒 Max wheel time is 180 seconds. Chill.")
        return

    message = await ctx.send(f"🎧 **Opt-in for Wheel has begun!**\nHit 🎧 to be considered. Winner will be randomly selected in **{seconds} seconds**.")
    await message.add_reaction("🎧")

    await asyncio.sleep(seconds)

    # Fetch updated message with reactions
    message = await ctx.channel.fetch_message(message.id)
    reaction = discord.utils.get(message.reactions, emoji="🎧")

    if not reaction:
        await ctx.send("⚠️ No one reacted in time.")
        return

    users = [user async for user in reaction.users()]
    users = [user for user in users if not user.bot]

    if not users:
        await ctx.send("⚠️ Nobody opted in! Spin canceled.")
        return

    winner = random.choice(users)
    await ctx.send(f"🎉 **{winner.mention} has been chosen by the Wheel of Fate!**")


poll_votes = {}  # message_id: {emoji: count}
user_votes = {} # message_id: {user_id: [emoji1, emoji2]}


def parse_duration(raw):
    if isinstance(raw, int):
        return raw
    match = re.match(r"(\d+)([mhd])", raw.lower())
    if not match:
        return int(raw)
    num, unit = int(match[1]), match[2]
    if unit == 'm':
        return num
    elif unit == 'h':
        return num * 60
    elif unit == 'd':
        return num * 1440
    return num

@bot.command(name="poll")
async def poll_command(ctx, *args):
    try:
        if len(args) == 0:
            await ctx.send("❌ You must provide a poll name.")
            return

        # Check for 'start' or 'stop' as the last argument
        if len(args) >= 2 and args[-1].lower() in ["start", "stop"]:
            poll_name = " ".join(args[:-1])
            action = args[-1].lower()
            poll_key = poll_name.lower()

            gid = str(ctx.guild.id)
            uid = str(ctx.author.id)

            if not (is_administrator(gid, uid) or is_organizer(gid, uid)):
                await ctx.send("🚫 You do not have permission to manage this poll.")
                return

            if poll_key not in active_polls:
                await ctx.send("⚠️ No active poll by that name.")
                return

            if action == "start":
                await start_poll(ctx, poll_key)
            elif action == "stop":
                await end_poll(ctx, poll_key)
            return

        # Extract name and other args
        name_parts = []
        i = 0
        while i < len(args) and not re.match(r"^\d+[mhd]?$", args[i]):
            name_parts.append(args[i])
            i += 1

        poll_name = " ".join(name_parts)
        poll_key = poll_name.lower()
        rest = args[i:]

        gid = str(ctx.guild.id)
        cid = str(ctx.channel.id)
        uid = str(ctx.author.id)

        # Permission check
        if not (is_administrator(gid, uid) or is_organizer(gid, uid)):
            await ctx.send("🚫 You do not have permission to start a poll.")
            return

        # Parse optional args with time suffix support
        submission_limit = int(rest[0]) if len(rest) >= 1 and rest[0].isdigit() else 1
        start_delay = parse_duration(rest[1]) if len(rest) >= 2 else 5
        vote_duration = parse_duration(rest[2]) if len(rest) >= 3 else 5
        vote_limit = int(rest[3]) if len(rest) >= 4 and rest[3].isdigit() else None

        if poll_key in active_polls:
            await ctx.send("⚠️ A poll with that name already exists. Use `!poll <name> start` or `stop`.")
            return

        # Create poll data
        now = datetime.utcnow()
        message = await ctx.send(f"📝 **Poll '{poll_name}' is open for submissions!**\nReply to this message with your entry.\nYou can submit **{submission_limit}** item(s). Voting will begin in **{start_delay}** minutes.")

        active_polls[poll_key] = {
            "guild_id": gid,
            "channel_id": cid,
            "creator_id": uid,
            "submission_limit": submission_limit,
            "start_time": now + timedelta(minutes=start_delay),
            "vote_duration": vote_duration,
            "vote_limit": vote_limit,
            "submissions": {},
            "status": "collecting",
            "message_id": message.id
        }

        # Schedule the vote to start automatically
        await asyncio.sleep(start_delay * 60)
        if active_polls.get(poll_key, {}).get("status") == "collecting":
            await start_poll(ctx, poll_key)

    except Exception as e:
        print(f"[ERROR] Poll command failed: {e}")
        await ctx.send(f"Error: {str(e)}")


async def start_poll(ctx, poll_key):
    poll = active_polls.get(poll_key)
    if not poll:
        return

    if poll["status"] != "collecting":
        await ctx.send("⚠️ Poll is already active or ended.")
        return

    poll["status"] = "voting"

    submissions = []
    for entries in poll["submissions"].values():
        submissions.extend(entries)

    if not submissions:
        await ctx.send("⚠️ No submissions were received. Poll cancelled.")
        active_polls.pop(poll_key, None)
        return

    channel = bot.get_channel(int(poll["channel_id"]))
    message_lines = [f"🗳️ **Voting for '{poll_key}' has begun!** React to vote:"]

    for i, entry in enumerate(submissions):
        message_lines.append(f"{i+1}. {entry}")

    vote_msg = await channel.send("\n".join(message_lines)) # type: ignore

    # React with emojis
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i in range(len(submissions)):
        await vote_msg.add_reaction(emojis[i])

    # Store the vote message ID to use later
    poll["vote_message_id"] = vote_msg.id
    poll["vote_emojis"] = emojis[:len(submissions)]
    poll["entries"] = submissions

    # Schedule poll end
    await asyncio.sleep(poll["vote_duration"] * 60)
    if poll_key in active_polls:
        await end_poll(ctx, poll_key)


async def end_poll(ctx, poll_key):
    poll = active_polls.get(poll_key)
    if not poll or poll["status"] != "voting":
        await ctx.send("⚠️ Poll is not currently active.")
        return

    poll["status"] = "ended"

    channel = bot.get_channel(int(poll["channel_id"]))
    vote_msg = await channel.fetch_message(poll["vote_message_id"]) # type: ignore

    vote_counts = {}
    for reaction in vote_msg.reactions:
        emoji = reaction.emoji
        if emoji in poll["vote_emojis"]:
            vote_counts[emoji] = reaction.count - 1  # Subtract bot's own reaction

    max_votes = max(vote_counts.values(), default=0)
    winners = [emoji for emoji, count in vote_counts.items() if count == max_votes and count > 0]

    result_lines = ["🏁 **Poll Results:**"]
    for emoji in poll["vote_emojis"]:
        entry = poll["entries"][poll["vote_emojis"].index(emoji)]
        count = vote_counts.get(emoji, 0)
        result_lines.append(f"{emoji} {entry} — {count} vote{'s' if count != 1 else ''}")

    if winners:
        if len(winners) == 1:
            winning_entry = poll["entries"][poll["vote_emojis"].index(winners[0])]
            result_lines.append(f"\n🏆 **Winner:** {winning_entry} with {max_votes} vote{'s' if max_votes != 1 else ''}!")
        else:
            tied_entries = [poll["entries"][poll["vote_emojis"].index(e)] for e in winners]
            result_lines.append(f"\n🤝 **Tie between:** {', '.join(tied_entries)} with {max_votes} votes each!")
    else:
        result_lines.append("\n❌ No votes were cast.")

    await channel.send("\n".join(result_lines)) # type: ignore
    active_polls.pop(poll_key, None)

@bot.command(name="lphelp")
async def lphelp_command(ctx):
    help_text = (
        "**🎵 Playlist Management**\n"
        "`!playlist add <name> to <channel>` - Create & assign playlist to channel (admins only)\n"
        "`!link` - Get Spotify link for current channel\n"
        "`!reset` - Reset playlist mapping for this channel (admins only)\n\n"
        "**➕ Adding Songs**\n"
        "`!add` - add the now playing track from spotify (requires spotify integration and discord online status)\n"
        "`!add <while replying to .fm bot command> - adds track based on fmbot results\n"
        "`!add <song> - <artist>`\n"
        "`!add <song> - <artist> - <album>`\n"
        "`!add <Spotify link>`\n\n"
        "**🚫 Removing Songs**\n"
        "`!remove <song title>` - Remove your submission\n\n"
        "**📊 Playlist Info & Limits**\n"
        "`!status` - Playlist size and your submissions\n"
        "`!quota <#>` - Set submission quota (organizers only)\n"
        "`!limit <#>` - Set track duration limit in minutes (organizers only)\n"
        "`!quota` / `!limit` - View current limits\n\n"
        "**📈 Leaderboard**\n"
        "`!leaderboard` - See top contributors\n\n"
        "**🕵️ Permissions**\n"
        "`!user @name` - Grant user (organizers only)\n"
        "`!organizer @name` - Grant organizer (admins only)\n"
        "`!administrator @name` - Grant admin (admins only)\n"
        "`!whoami` - Check your permission level\n\n"
        "**🎨 Art Settings**\n"
        "`!art on/off` - Enable or disable art (admins only)\n"
        "`!prompt` - Generate an AI art prompt"
        "`!artchannel <channel>` - Set art image post channel (admins only)\n"
        "`!refreshart` - Refresh playlist artwork (organizers only if art is enabled)\n\n"
        "**🎧 LP Tools**\n"
        "`!countdown [reactions_needed]` - Start group countdown to play\n"
        "`!wheel` [reactions_needed]` - Randomly select a wheel participant\n"
        "`!poll <# of user selections> <# of minutes, hours, or day for poll open> <# of m,h.d, for vote> <# of votes> "
    )
    await ctx.send(help_text)

print("[BEFORE RUN] Permissions content:")
print(json.dumps(permissions, indent=2))


bot.run(DISCORD_TOKEN) # type: ignore
