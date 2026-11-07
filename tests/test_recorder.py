import numpy as np

from jarvis.voice.recorder import BLOCK, Segmenter


def noise(level=0.002):
    return (np.random.default_rng(0).standard_normal(BLOCK) * level).astype("float32")


def speech(level=0.2):
    t = np.arange(BLOCK) / 16_000
    return (np.sin(2 * np.pi * 220 * t) * level).astype("float32")


def feed_all(seg, blocks):
    for i, b in enumerate(blocks):
        if seg.feed(b):
            return i
    return None


def test_stops_after_silence_following_speech():
    seg = Segmenter(silence_seconds=0.5)
    blocks = [noise()] * 5 + [speech()] * 10 + [noise()] * 20
    stopped_at = feed_all(seg, blocks)
    assert stopped_at == 5 + 10 + 5 - 1  # 0.5 s = 5 blok jimlikdan keyin
    audio = seg.audio()
    assert len(audio) >= 10 * BLOCK  # butun gap saqlangan
    assert np.abs(audio).max() > 0.1


def test_gives_up_when_nobody_speaks():
    seg = Segmenter(start_timeout=1.0)
    assert feed_all(seg, [noise()] * 30) == 9
    assert len(seg.audio()) == 0


def test_max_length():
    seg = Segmenter(max_seconds=2.0)
    stopped_at = feed_all(seg, [noise()] * 3 + [speech()] * 100)
    assert stopped_at is not None and stopped_at < 30


def test_threshold_adapts_to_noisy_room():
    seg = Segmenter()
    for _ in range(3):
        seg.feed(noise(0.05))  # shovqinli xona
    assert seg.threshold > 0.1
    assert not seg.feed(noise(0.05))  # shovqin gap deb olinmaydi
    assert not seg.started
