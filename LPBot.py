import discord
from discord.ext import commands
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json
from dotenv import load_dotenv
import asyncio

import logging
logging.getLogger('discord').setLevel(logging.WARNING)

# === LOAD ENV ===
load_dotenv()

PERMISSIONS_FILE = "permissions.json"

if os.path.exists(PERMISSIONS_FILE):
    with open(PERMISSIONS_FILE, "r") as f:
        permissions = json.load(f)
else:
    permissions = {"organizers": [], "users": []}

#In the below config section, I use environment variables to manage my Tokens and Secrets.
#Keep these keys secure!!!

# === CONFIG ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")



# === INTENTS ===
intents = discord.Intents.default()
intents.message_content = True

# === BOT CONFIG ===
bot = commands.Bot(command_prefix="!", intents=intents)

# === SPOTIFY AUTH ===
scope = "playlist-modify-public playlist-modify-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=scope
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

if os.path.exists(PLAYLIST_MAP_FILE):
    with open(PLAYLIST_MAP_FILE, "r") as f:
        playlist_map = json.load(f)
else:
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

    except Exception as e:
        print(f"[ERROR] {e}")
        await ctx.send(f"Error: {str(e)}")

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
def is_organizer(user_id):
    return str(user_id) in permissions.get("organizers", [])

def is_user(user_id):
    return str(user_id) in permissions.get("users", []) or is_organizer(user_id)

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")
    for guild in bot.guilds:
        inviter = None
        try:
            invites = await guild.invites()
            for invite in invites:
                if invite.inviter:
                    inviter = invite.inviter
                    break
        except Exception as e:
            print(f"[ERROR] Could not fetch invites for {guild.name}: {e}")
            continue

        if inviter:
            uid = str(inviter.id)
            if uid not in permissions["organizers"]:
                permissions["organizers"].append(uid)
                print(f"[INFO] Added {inviter} as organizer for {guild.name}")

        for member in guild.members:
            uid = str(member.id)
            if uid not in permissions["organizers"] and uid not in permissions["users"]:
                permissions["users"].append(uid)

    with open(PERMISSIONS_FILE, "w") as f:
        json.dump(permissions, f)

# Uncomment these if you need better debugging
# @bot.event
# async def on_message(message):
#     #print(f"[DEBUG] Received message from {message.author}: {message.content}")
#     await bot.process_commands(message)

@bot.command(name="user")
async def add_user_permission(ctx, member: discord.Member):
    if not is_organizer(ctx.author.id):
        await ctx.send("You do not have permission to assign roles.")
        return
    uid = str(member.id)
    if uid not in permissions["users"]:
        permissions["users"].append(uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f)
    await ctx.send(f"User {member.display_name} granted user permissions.")

@bot.command(name="organizer")
async def add_organizer_permission(ctx, member: discord.Member):
    if not is_organizer(ctx.author.id):
        await ctx.send("You do not have permission to assign organizer roles.")
        return
    uid = str(member.id)
    if uid not in permissions["organizers"]:
        permissions["organizers"].append(uid)
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f)
    await ctx.send(f"User {member.display_name} granted organizer permissions.")

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
        "`!playlist add <name> to <channel>` - Create & assign playlist to channel\n"
        "`!link` - Get Spotify link for current channel\n"
        "`!reset` - Reset playlist mapping for this channel\n\n"
        "**➕ Adding Songs**\n"
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
        "`!user @name` - Grant user\n"
        "`!organizer @name` - Grant organizer\n"
        "`!whoami` - Check your permission level\n\n"
        "**⏱️ Countdown Mode**\n"
        "`!countdown [reactions_needed]` - Start group countdown to play"
    )
    await ctx.send(help_text)


bot.run(DISCORD_TOKEN)
