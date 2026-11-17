---
name: stream-clipper
description: Find the best moments in a long stream by reading its chat, and cut them into vertical 9:16 Shorts. Use when the user gives a YouTube live replay URL (or a Twitch chat JSON + VOD) and wants clips, highlights or Shorts from it, e.g. GTA 6 launch streams.
---

# Stream clipper

Chat reacts after something happens, so the moments are where chat spikes. `clipper.py` (in the repo root) does it all.

1. Check the tools: `python -m yt_dlp --version` and `ffmpeg -version`. If yt-dlp is missing: `pip install "yt-dlp[default]"`
   (the `[default]` extra brings the JS challenge solver; without it YouTube gives 480p only).
2. Look first, cut second. Run a dry run and show the user the list:
   `python clipper.py "<url>" --top 10 --dry-run --out clips/<name>`
   Each line: time, a bar, how many different people, how far above normal, and what chat said.
3. Ask which to cut (or cut them all), then: `python clipper.py "<url>" --chat clips/<name>/stream.live_chat.json --top N --out clips/<name>`
   Only the clip's own seconds are downloaded, never the whole stream.
4. Open a few frames of each clip before calling it done (`ffmpeg -i clip.mp4 -vf fps=1/4,scale=180:-1,tile=10x1 sheet.jpg`).
   Chat spikes are a good guess, not a guarantee: say which clips are misses.
5. Captions (Apple silicon, local Whisper): `pip install mlx-whisper pillow`, then add `--captions`.
6. Twitch: download chat with TwitchDownloaderCLI (`chatdownload --id <vod> -o chat.json`) and the VOD, then
   `python clipper.py --chat chat.json --video vod.mp4`.

`spikes.json` in the output folder has the whole chat curve and, per clip, what chat said (title ideas).

Rules for the user: clip only streamers who allow it (many have a clipping policy or a clipping program), credit them,
and don't re-upload whole streams.
