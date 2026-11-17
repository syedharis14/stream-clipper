"""Each test is a way the clipper went wrong on a real stream (see the process log)."""
import json
import clipper as c


def yt_line(sec, who, text, badge=None):
    r = {"message": {"runs": [{"text": text}]}, "authorExternalChannelId": who}
    if badge:
        r["authorBadges"] = [{"liveChatAuthorBadgeRenderer": {"icon": {"iconType": badge}}}]
    return json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(int(sec * 1000)),
                       "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": r}}}]}})


def chat(tmp_path, lines):
    p = tmp_path / "s.live_chat.json"
    p.write_text("\n".join(lines))
    return c.read_chat(str(p))


def quiet_stream(minutes=20):
    """Two people chatting calmly, one message every 5 s: the stream's 'normal'."""
    return [yt_line(t, f"u{t % 2}", "nice car") for t in range(0, minutes * 60, 5)]


def test_bots_mods_and_streamer_are_not_chat(tmp_path):
    msgs = chat(tmp_path, [yt_line(1, "Nightbot", "STAY CONNECTED WITH NINJA"),
                           yt_line(2, "m1", "no links", "MODERATOR"),
                           yt_line(3, "me", "thanks for watching", "OWNER"),
                           yt_line(4, "v1", "LMAO")])
    assert [m[2] for m in msgs] == ["LMAO"]


def test_greetings_are_not_reactions(tmp_path):
    msgs = chat(tmp_path, [yt_line(1, "a", "hi"), yt_line(2, "b", "Hello bro"), yt_line(3, "c", "salam!!"),
                           yt_line(4, "d", "hi he just crashed the plane")])
    assert [m[2] for m in msgs] == ["hi he just crashed the plane"]


def test_one_spammer_is_not_a_spike(tmp_path):
    lines = quiet_stream() + [yt_line(600 + i * 0.2, "spammer", "LMAO") for i in range(40)]
    score, _, r = c.buckets(chat(tmp_path, lines))
    assert c.find_spikes(score, 5, _, r) == []


def test_twenty_people_laughing_is_a_spike_and_clip_starts_30s_early(tmp_path):
    lines = quiet_stream() + [yt_line(603, f"v{i}", "LMAOOO 😂") for i in range(20)]
    score, _, r = c.buckets(chat(tmp_path, lines))
    spikes = c.find_spikes(score, 5, _, r)
    assert [i * c.WINDOW for _, i in spikes] == [600]
    assert c.clip_range(spikes[0][1]) == (570, 610)   # chat was 12-15 s late on Kai's stream


def test_reactions_beat_the_same_number_of_people_just_talking(tmp_path):
    lines = (quiet_stream()
             + [yt_line(300 + i * 0.1, f"t{i}", "name le lo bhai") for i in range(8)]
             + [yt_line(900 + i * 0.1, f"r{i}", "NO WAY 💀") for i in range(8)])
    score, _, r = c.buckets(chat(tmp_path, lines))
    assert score[90] > 2 * score[30]


def test_hellos_and_goodbyes_at_the_ends_are_skipped(tmp_path):
    lines = ([yt_line(5 + i * 0.1, f"a{i}", "LMAO lets go") for i in range(30)] + quiet_stream()
             + [yt_line(1195 + i * 0.1, f"b{i}", "GG bye 😭") for i in range(30)])
    score, _, r = c.buckets(chat(tmp_path, lines))
    assert c.find_spikes(score, 5, _, r) == []


def test_two_spikes_in_one_clip_become_one(tmp_path):
    lines = quiet_stream() + [yt_line(t, f"v{t}{i}", "OMG") for t in (600, 620) for i in range(20)]
    score, _, r = c.buckets(chat(tmp_path, lines))
    assert len(c.find_spikes(score, 5, _, r)) == 1


def test_a_short_never_runs_past_58_seconds():
    a, b = c.clip_range(100)
    assert b - a <= c.MAX_LEN


def test_chat_answering_a_question_is_not_a_moment(tmp_path):
    """Kai asked "is it lagging?": 80 people typed YES / NO / LAG. Biggest spike of the stream, nothing happened."""
    lines = quiet_stream() + [yt_line(600 + i * 0.1, f"a{i}", ["YES", "NO", "LAG", "MIAMI"][i % 4]) for i in range(80)]
    score, _, r = c.buckets(chat(tmp_path, lines))
    assert c.find_spikes(score, 5, _, r) == []


def test_captions_drop_unsure_words_and_split_on_pauses():
    w = [{"word": " oh", "start": 0.0, "end": 0.3, "probability": 0.9}, {"word": " my", "start": 0.3, "end": 0.5, "probability": 0.9},
         {"word": " xyz", "start": 0.5, "end": 0.7, "probability": 0.05}, {"word": " god", "start": 0.7, "end": 1.0, "probability": 0.9},
         {"word": " wasted", "start": 3.0, "end": 3.5, "probability": 0.8}]
    assert [g[2] for g in c.caption_groups(w)] == ["OH MY GOD", "WASTED"]
