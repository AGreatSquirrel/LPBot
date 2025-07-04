🎧 LPBot Setup Guide

Welcome to LPBot! This bot helps manage community playlist submissions for Discord listening parties using Spotify. Follow this guide to get up and running.

🚀 Prerequisites

Python 3.13+

A Discord account and server

Spotify account (Premium not required for creating playlists)

Spotify Developer account

Discord Developer Portal access

🔧 Installation Steps

1. Clone the Repository

git clone https://github.com/AGreatSquirrel/LPBot.git
cd LPBot

2. Create a Virtual Environment (Optional but Recommended)

python -m venv .venv
source .venv/bin/activate   # On Windows use: .venv\Scripts\activate

3. Install Dependencies

pip install -r requirements.txt

4. Set Up Environment Variables

Create a .env file in the root folder with the following:

DISCORD_TOKEN=your_discord_bot_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

🎮 Bot Setup

1. Create Your Discord Bot

Go to Discord Developer Portal

Create a new application

Enable Message Content Intent

Create a Bot, copy the token, and add it to your .env

Under OAuth2 > URL Generator:

Check bot and applications.commands

Select permissions: Send Messages, Read Message History, Manage Messages, etc.

Copy the generated URL and invite the bot to your server

2. Set Up Spotify App

Go to Spotify Developer Dashboard

Create an App

Add http://localhost:8888/callback as a redirect URI

Use the Client ID and Secret in your .env

▶️ Run the Bot

python lpbot.py

If successful, the bot will print a "Logged in as..." message.

🛠️ Usage

Use !lphelp in any Discord channel the bot is in to see a list of available commands.

🗃️ File Descriptions

lpbot.py: Main bot script

.env: Environment config (do not commit this!)

permissions.json: Tracks roles per server

submissions.json: Tracks user submissions

playlist_map.json: Maps channels to playlists

quotas.json: Playlist quota per user

limits.json: Song length limits

🙋 Support

Open an issue on GitHub or reach out in the Discord server where this bot is active.

Happy listening! 🎶
