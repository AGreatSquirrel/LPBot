#  LPBot – The Discord Listening Party Bot
A Discord bot that lets users collaboratively build Spotify playlists, track submissions, enforce song limits, and run synchronized countdowns for group listening parties.

Built for music nerds. Powered by Python + Spotify + Discord.

---

##  Features

- ! commands to contribute tracks by name or link
- Auto-links playlists to Discord channels
- Per-channel quotas & song length limits
- Album art previews
- Countdown start with emoji reactions
- User/Organizer permissions
- Leaderboards, status reports, and more!
- Custom AI generated artwork for playlists


## Examples

-!playlist add Group-Playlist to Music                            #Adds a playlist called 'Group-Playlist to the Music Channel of a discord server 
-!add For Whom the Bell Tolls - Metallica                         #Adds a song to the channels playlist by Song Name - Band Name
-!add For Whom the Bell Tolls - Metallica - Ride the Lightning    #Adds a song to the channels playlist by Song Name - Band Name - Album Name
-!add <spotify track URL>                                         #Adds a song to the channels playlist by Spotify URL
-!remove For Whom the Bell Tolls                                  #Removes song from the channels playlist
-!link                                                            #Retreives a link to the channels playlist
-!countdown 3                                                     #Starts a countdown which requires a specific number of users to react to, to initiate
-!reset                                                           #Resets playlist mapping for the channel
-!status                                                          #Shows songs in the current playlist and who submitted them
-!quota 3                                                         #Sets a limit on the number of songs able to be submitted to the channels playlist
-!limit 10                                                        #Sets a limit in minutes for the max playtime a song can be
-!leaderboards                                                    #Displays top contributers to the channels playlist
-!user                                                            #sets user level permissions for the bot
-!organizer                                                       #sets organizer level permissions for the bot
-!lphelp                                                          #displays available bot commands 
-!art <on/off>                                                    #enable channel artwork
-!refreshart`                                                     #geneates new playlist art

##  Permissions Overview

| Command / Feature                          | Organizer     | User       |
|--------------------------------------------|---------------|------------|
| `!add <song>`                              | ✅            | ✅        |
| `!remove <song>`                           | ✅            | ✅ *(own only)* |
| `!playlist add <name> to <#channel>`       | ✅            | ❌        |
| `!quota <#>` *(set user submission cap)*   | ✅            | ❌        |
| `!limit <#>` *(set track duration limit)*  | ✅            | ❌        |
| `!quota` *(view current cap)*              | ✅            | ✅        |
| `!limit` *(view duration limit)*           | ✅            | ✅        |
| `!status` *(view your submissions)*        | ✅            | ✅        |
| `!link` *(get playlist link)*              | ✅            | ✅        |
| `!leaderboard` *(top submitters)*          | ✅            | ✅        |
| `!countdown [#]` *(reaction-based start)*  | ✅            | ✅        |
| `!user @mention` *(grant user role)*       | ✅            | ❌        |
| `!organizer @mention` *(grant organizer)*  | ✅            | ❌        |
| `!whoami` *(check your role)*              | ✅            | ✅        |
| `!lphelp` *(view all commands)*            | ✅            | ✅        |
| `!art <on/off>`                            | ✅            | ❌        |
| `!refreshart`                              | ✅            | ❌        |

If you liked this project, consider buying me a coffee
https://coff.ee/agreatsquirrel
