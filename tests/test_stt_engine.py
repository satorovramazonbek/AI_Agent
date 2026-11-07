import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.voice import stt

HAS_MLX = importlib.util.find_spec("mlx_whisper") is not None


def settings(tmp_path, engine="auto", with_model=True):
    model = tmp_path / "uz-mlx"
    if with_model:
        model.mkdir()
        (model / "weights.safetensors").write_bytes(b"")
    return SimpleNamespace(stt_engine=engine, stt_mlx_model=model, stt_language="uz",
                           stt_model="ct2-model", stt_use_hints=False, stt_prompt="")  # fmt: skip


@pytest.fixture(autouse=True)
def fresh():
    stt.get_transcriber.cache_clear()
    yield
    stt.get_transcriber.cache_clear()


def test_ct2_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "get_settings", lambda: settings(tmp_path, "ct2"))
    assert isinstance(stt.get_transcriber(), stt.Transcriber)


def test_auto_without_model_falls_back_to_ct2(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "get_settings", lambda: settings(tmp_path, with_model=False))
    assert isinstance(stt.get_transcriber(), stt.Transcriber)


def test_auto_on_linux_uses_ct2(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "get_settings", lambda: settings(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    assert isinstance(stt.get_transcriber(), stt.Transcriber)


@pytest.mark.skipif(not HAS_MLX or sys.platform != "darwin", reason="MLX faqat Apple Silicon'da")
def test_auto_with_model_uses_mlx(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "get_settings", lambda: settings(tmp_path))
    t = stt.get_transcriber()
    assert isinstance(t, stt.MlxTranscriber) and t.model_name.endswith("uz-mlx")


@pytest.mark.skipif(not HAS_MLX, reason="mlx o'rnatilmagan")
def test_converter_name_mapping():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from convert_mlx import map_name

    assert map_name("model.encoder.conv1.weight") == "encoder.conv1.weight"
    assert map_name("model.encoder.layers.3.self_attn.q_proj.weight") == (
        "encoder.blocks.3.attn.query.weight"
    )
    assert map_name("model.decoder.layers.1.encoder_attn.k_proj.weight") == (
        "decoder.blocks.1.cross_attn.key.weight"
    )
    assert map_name("model.decoder.layers.0.final_layer_norm.bias") == (
        "decoder.blocks.0.mlp_ln.bias"
    )
    assert map_name("model.decoder.embed_positions.weight") == "decoder.positional_embedding"
    assert map_name("model.encoder.embed_positions.weight") is None
    assert map_name("proj_out.weight") is None
    with pytest.raises(KeyError):
        map_name("model.something.unknown.weight")
