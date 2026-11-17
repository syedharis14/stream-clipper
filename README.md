# stream-clipper

Find the moments chat lost its mind in a long stream, and cut them into vertical Shorts. Built with Claude Code for the
GTA 6 launch (19 Nov 2026), when every streamer is live for six hours or more.

```bash
git clone https://github.com/syedharis14/stream-clipper && cd stream-clipper
python3 -m venv .venv && .venv/bin/pip install "yt-dlp[default]" pytest   # ffmpeg from your package manager
.venv/bin/python clipper.py "https://www.youtube.com/watch?v=<live replay>" --top 10 --dry-run   # look first
.venv/bin/python clipper.py "https://www.youtube.com/watch?v=<live replay>" --top 10             # then cut
```

Captions (optional, Apple silicon, runs locally): `.venv/bin/pip install mlx-whisper pillow`, then add `--captions`.
Tests: `.venv/bin/python -m pytest -q`.

How it decides, and why (each rule is a way it went wrong on a real stream; each has a test in `test_clipper.py`):

| Rule | Why |
|---|---|
| Count **people** per 10 s, not messages | one spammer typing LMAO 40 times scored as a spike |
| Drop the streamer, moderators, bots and plain "hi"s | "STAY CONNECTED WITH..." bots and stream-start hellos were the top spikes |
| Reactions (LMAO, 😂, NO WAY, W) count 3, chatting counts 1 | busy is not funny: shout-out requests filled a whole stream's top 10 |
| At least 30% of the people in a spike must be reacting | "Is it lagging?" got 80 people typing YES / NO: the biggest spike, nothing happened |
| A spike needs 6 different people | quiet stretches made 3 people look like a spike |
| Compare with the 5 minutes around it | a busy hour is not one long spike |
| Start 30 s before the spike, end 10 s after | on a real 11-hour stream, chat was 12-15 s behind the moment |
| Cut out black stretches | loading screens after a death ate 9 s of a 40 s clip |
| Skip the first and last 2 minutes | hellos and goodbyes |

It downloads only each clip's own seconds (`yt-dlp --download-sections`), not the whole stream.
As a Claude Code skill: open the repo in Claude Code and ask it to clip a stream (`.claude/skills/stream-clipper/SKILL.md`).

**Clip responsibly:** only streamers who allow it (check their clipping policy or program), credit them, don't re-upload streams.
Chat spikes are a good guess, not a guarantee: watch your clips before posting.

MIT licensed: see `LICENSE`.
