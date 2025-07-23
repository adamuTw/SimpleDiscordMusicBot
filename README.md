# SimpleDiscordMusicBot
A simple Discord music bot can play YouTube videos in a voice channel.

# Step:

1.create an Applications on https://discord.com/developers/applications
<img width="2559" height="1252" alt="螢幕擷取畫面 2025-07-23 203515" src="https://github.com/user-attachments/assets/53514d85-4e65-4c54-9695-70f4db84fe44" />

2.enable "Message Content Intent"、"Server Members Intent"、"Presence Intent" in Bot menu
<img width="2559" height="1255" alt="image" src="https://github.com/user-attachments/assets/2ac4c15e-b844-4372-b47b-41bd38dbd675" />

3.set "Installation Contexts" in Installation menu to "Guild Install" only
<img width="2559" height="1254" alt="image" src="https://github.com/user-attachments/assets/360a340e-c1ff-4573-8c5a-df9a8ba2f106" />

4.set "Default Install Settings" in Installation menun like the picture
<img width="2559" height="1255" alt="image" src="https://github.com/user-attachments/assets/fe7f6ce6-58e5-4cd7-9485-ceb3936eb174" />

5.get your bot token in bot menu(while you press the reset button,your token will display once,please keep this token-key)
<img width="2559" height="1252" alt="螢幕擷取畫面 2025-07-23 204805" src="https://github.com/user-attachments/assets/3de3c74d-bad2-4dde-bee1-683b35a195b3" />

6.download automu.py and move it to your bot menu

7.edit automu.py at line 459,and change the token to your(you will get it at step.5)

6.build a Docker container by using python:3.13.0 and run "sh -c "apt-get update && apt-get install -y ffmpeg && pip install discord.py PyNaCl yt_dlp && python3 /your_bot_menu/automu.py" and enable it


# Now you can invite this bot to your server and enjoy it!
