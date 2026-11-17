#!/usr/bin/env python3
"""stream-clipper: find the moments chat lost its mind, and cut them into vertical Shorts.

    python clipper.py <youtube-url>               # chat -> spikes -> clips, all in one
    python clipper.py <url> --top 8 --dry-run     # just show the spikes, cut nothing
    python clipper.py --chat twitch_chat.json --video vod.mp4   # Twitch: TwitchDownloader chat + local VOD
    python clipper.py <url> --captions            # + captions from local Whisper (free, on your Mac)

How it works: chat reacts AFTER something happens. So we count chat messages in 10-second windows,
compare each window with the stream's own normal level (a busy stream is not one long spike), give
extra weight to reaction words (LMAO, OMG, CLIP IT...), and cut each spike starting 20 s early.
"""
import argparse, json, os, re, statistics, subprocess, sys
from collections import Counter

WINDOW = 10        # seconds per bucket
LEAD = 30          # chat reacts late (12-15 s on Kai's stream, measured): start the clip 30 s before the spike
TAIL = 10          # and keep 10 s after it
BLACK = 1.5        # cut out black stretches longer than this (90% of the frame black: the webcam and chat box stay on top)
MAX_LEN = 58       # a Short stays under 60 s
BASELINE = 30      # buckets either side (5 min) that define "normal" for this part of the stream
MIN_REACT = 0.3   # ...and at least 30% of them reacting. "Is it lagging?" gets 80 people typing YES/NO: not a moment
MIN_PEOPLE = 6     # a spike needs at least this many different people in its 10 s
SKIP_ENDS = 120    # the first and last 2 minutes are hellos and goodbyes, not moments
GREETING = re.compile(r"^\W*(hi+|hello+|hey+|yo+|salam|assalam\w*|namaste|gm|good (morning|evening))\W*(\w+\W*)?$", re.I)
HYPE = re.compile(r"\b(lmao+|lmfao|lol+|omg+|wtf|bro+|no way|clip (it|that)|kekw|lul|w+|l+|insane|holy|ha(ha)+h*|he(he)+|xd+)\b"
                  r"|😂|🤣|💀|😭|😱|🔥|‼|!!!|:face_with_tears_of_joy:|:rolling_on_the_floor_laughing:|:skull:", re.I)


# ---------- 1. chat ----------------------------------------------------------------------------------
def download_chat(url, out):
    """YouTube live replays: yt-dlp saves the chat as JSON lines, no video."""
    subprocess.run([sys.executable, "-m", "yt_dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
                    "-o", os.path.join(out, "stream"), url], check=True)
    return os.path.join(out, "stream.live_chat.json")


def read_chat(path):
    """-> [(seconds, author, text)] from viewers only. Reads yt-dlp's YouTube chat or TwitchDownloader's Twitch chat.
    Dropped: the streamer, moderators, bots ("STAY CONNECTED...", "MERCH LIVE...") and plain greetings."""
    msgs = []
    with open(path, encoding="utf-8") as f:
        head = f.read(1); f.seek(0)
        if head == "{" and path.endswith(".live_chat.json"):           # YouTube: one JSON object per line
            for line in f:
                a = json.loads(line).get("replayChatItemAction", {})
                for act in a.get("actions", []):
                    r = act.get("addChatItemAction", {}).get("item", {}).get("liveChatTextMessageRenderer")
                    if not r or "message" not in r:
                        continue
                    badges = json.dumps(r.get("authorBadges", []))
                    if "MODERATOR" in badges or "OWNER" in badges or "VERIFIED" in badges:
                        continue
                    text = "".join(run.get("text") or run.get("emoji", {}).get("shortcuts", [""])[0]
                                   for run in r["message"]["runs"])
                    msgs.append((int(a["videoOffsetTimeMsec"]) / 1000, r.get("authorExternalChannelId", ""), text))
        else:                                                             # Twitch: TwitchDownloaderCLI chatdownload
            for c in json.load(f)["comments"]:
                badges = {b.get("_id") for b in c["message"].get("user_badges") or []}
                if badges & {"broadcaster", "moderator"}:
                    continue
                msgs.append((c["content_offset_seconds"], c["commenter"]["name"], c["message"]["body"]))
    return sorted((t, who, text) for t, who, text in msgs
                  if t >= 0 and "bot" not in who.lower() and not GREETING.match(text))


# ---------- 2. spikes --------------------------------------------------------------------------------
def buckets(msgs):
    """People (not messages) per 10 s window, so one spammer can't fake a spike.
    Busy is not funny: someone reacting (LMAO, 😂, NO WAY) counts 3, someone just chatting counts 1."""
    n = int(msgs[-1][0] // WINDOW) + 1
    people = [set() for _ in range(n)]
    hypers = [set() for _ in range(n)]
    for t, who, text in msgs:
        i = int(t // WINDOW)
        people[i].add(who)
        if HYPE.search(text):
            hypers[i].add(who)
    count = [len(p) for p in people]
    score = [c + 2 * len(h) for c, h in zip(count, hypers)]
    edge = SKIP_ENDS // WINDOW
    score[:edge] = [0] * min(edge, n)
    score[-edge:] = [0] * min(edge, n)
    react = [len(h) for h in hypers]
    return score, count, react


def find_spikes(score, top, count=None, react=None):
    """Score each window against the median of the 5 minutes around it; keep the top, never overlapping."""
    rated = []
    for i, s in enumerate(score):
        if count is not None and count[i] < MIN_PEOPLE:
            continue
        if react is not None and react[i] < MIN_REACT * count[i]:   # chat answering a question
            continue
        around = score[max(0, i - BASELINE):i] + score[i + 1:i + 1 + BASELINE]
        base = max(statistics.median(around) if around else 0, 2)
        rated.append((s / base, i))
    picked = []
    for ratio, i in sorted(rated, reverse=True):
        if ratio < 2.5 or len(picked) == top:
            break
        if all(abs(i - j) * WINDOW > LEAD + TAIL for _, j in picked):   # merge spikes that share a clip
            picked.append((ratio, i))
    return sorted(picked, key=lambda p: p[1])


def clip_range(i):
    peak = i * WINDOW
    start = max(0, peak - LEAD)
    return start, min(peak + TAIL, start + MAX_LEN)


def what_chat_said(msgs, a, b, k=5):
    """The most repeated messages in the spike: free title ideas."""
    said = Counter(text.strip().upper() for t, _, text in msgs if a <= t < b and text.strip())
    return [w for w, _ in said.most_common(k)]


# ---------- 3. clips ---------------------------------------------------------------------------------
def vertical(black):
    """ffmpeg graph: drop the black stretches (picture and sound together), then a 9:16 frame:
    the whole picture in the middle, a blurred, darker copy of it filling the rest."""
    keep = "*".join(f"not(between(t,{a:.2f},{b:.2f}))" for a, b in black) or "1"
    return (f"[0:v]select='{keep}',setpts=N/FRAME_RATE/TB,split[v1][v2];"
            f"[0:a]aselect='{keep}',asetpts=N/SR/TB[a];"
            "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:3,eq=brightness=-0.15[bg];"
            "[v2]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[v]")


def black_runs(src, ss):
    """[(start, end)] of black stretches longer than BLACK seconds (loading screens), via ffmpeg's blackdetect."""
    r = subprocess.run(["ffmpeg", "-hide_banner", *ss, "-i", src, "-vf", f"blackdetect=d={BLACK}:pix_th=0.12:pic_th=0.90", "-an", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r)]


def cut(url, video, start, end, out):
    """Cut one clip; returns how many seconds of black screen were removed."""
    if video:                                    # a local file: cut straight from it
        src, ss = video, ["-ss", str(start), "-to", str(end)]
    else:                                        # a URL: download only these seconds, not the 6-hour stream
        src = out.replace(".mp4", ".src.mp4")
        subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "-f", "bv*[height<=1920][width<=1920]+ba/b", "--force-keyframes-at-cuts",
                        "--download-sections", f"*{start}-{end}", "--merge-output-format", "mp4", "-o", src, url], check=True)
        ss = []
    black = black_runs(src, ss)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ss, "-i", src, "-filter_complex", vertical(black), "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k", out], check=True)
    if not video:
        os.remove(src)
    return sum(b - a for a, b in black)


# ---------- 4. captions (optional, local Whisper: free, nothing leaves the Mac) ------------------------------
WHISPER = "mlx-community/whisper-large-v3-turbo"
FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def caption_groups(words, max_words=3, min_prob=0.25):
    """Whisper words -> [(start, end, text)]: 1-3 words a card, unsure words dropped (game audio confuses it)."""
    words = [w for w in words if w.get("probability", 1) >= min_prob and w["word"].strip()]
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) == max_words or w["start"] - cur[-1]["end"] > 0.6):
            groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return [(g[0]["start"], max(g[-1]["end"], g[0]["start"] + 0.5), " ".join(x["word"].strip() for x in g).upper()) for g in groups]


def caption_png(text, path):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONT, 84)
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = d.textbbox((0, 0), text, font=font, stroke_width=10)
    img = Image.new("RGBA", (r - l + 40, b - t + 40), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((20 - l, 20 - t), text, font=font, fill="white", stroke_width=10, stroke_fill="black")
    img.save(path)


def add_captions(clip):
    """Transcribe the finished clip with Whisper, then lay each caption over it (this ffmpeg has no subtitle filter)."""
    import mlx_whisper, tempfile
    r = mlx_whisper.transcribe(clip, path_or_hf_repo=WHISPER, word_timestamps=True)
    groups = caption_groups([w for s in r["segments"] for w in s.get("words", [])])
    if not groups:
        return 0
    with tempfile.TemporaryDirectory() as d:
        ins, graph, last = [], [], "0:v"
        for k, (a, b, text) in enumerate(groups):
            png = os.path.join(d, f"c{k}.png"); caption_png(text, png); ins += ["-i", png]
            graph.append(f"[{last}][{k + 1}:v]overlay=(W-w)/2:1380:enable='between(t,{a:.2f},{b:.2f})'[o{k}]")
            last = f"o{k}"
        out = clip.replace(".mp4", ".cap.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, *ins, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-map", "0:a",
                        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "copy", out], check=True)
        os.replace(out, clip)
    return len(groups)


def stamp(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def bar(v, top):
    return "█" * round(30 * v / top)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="YouTube live replay URL")
    ap.add_argument("--chat", help="chat file instead of downloading (yt-dlp .live_chat.json or TwitchDownloader .json)")
    ap.add_argument("--video", help="local video to cut from instead of downloading sections")
    ap.add_argument("--top", type=int, default=10, help="how many clips (default 10)")
    ap.add_argument("--out", default="clips")
    ap.add_argument("--dry-run", action="store_true", help="find the spikes, cut nothing")
    ap.add_argument("--captions", action="store_true", help="burn in captions from local Whisper (mlx-whisper, Apple silicon)")
    a = ap.parse_args()
    if not (a.chat or a.url):
        ap.error("give a URL or --chat")
    os.makedirs(a.out, exist_ok=True)

    chat = a.chat or download_chat(a.url, a.out)
    msgs = read_chat(chat)
    score, count, react = buckets(msgs)
    spikes = find_spikes(score, a.top, count, react)
    print(f"{len(msgs):,} chat messages over {stamp(msgs[-1][0])}  ·  normal: {statistics.median(count)} people per {WINDOW}s")
    print(f"{len(spikes)} spikes\n")

    report = []
    top = max(score[i] for _, i in spikes) if spikes else 1
    for n, (ratio, i) in enumerate(spikes, 1):
        a_, b_ = clip_range(i)
        said = what_chat_said(msgs, i * WINDOW, (i + 1) * WINDOW)
        print(f"#{n:<2} {stamp(i * WINDOW)}  {bar(score[i], top):<30} {count[i]:>3} people  {ratio:4.1f}x  {' · '.join(said[:3])[:40]}")
        clip = os.path.join(a.out, f"clip{n:02d}_{stamp(i * WINDOW).replace(':', '-')}.mp4")
        report.append({"n": n, "peak": i * WINDOW, "start": a_, "end": b_, "people": count[i],
                       "ratio": round(ratio, 1), "chat_said": said, "file": os.path.basename(clip)})
        if not a.dry_run:
            gone = cut(a.url, a.video, a_, b_, clip)
            if gone:
                print(f"    cut {gone:.0f} s of black screen out of #{n}")
            if a.captions:
                print(f"    {add_captions(clip)} captions on #{n}")

    json.dump({"window": WINDOW, "counts": count, "score": score, "clips": report},
              open(os.path.join(a.out, "spikes.json"), "w"), ensure_ascii=False, indent=1)
    print(f"\n{'found' if a.dry_run else 'cut'} {len(report)} clips -> {a.out}/")


if __name__ == "__main__":
    main()
