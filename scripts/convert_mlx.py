"""Hugging Face (transformers) Whisper modelini mlx-whisper formatiga o'giradi.

    .venv/bin/python scripts/convert_mlx.py qirol4006/Whisper-3-turbo-uzbek

Natija: ~/Library/Application Support/JARVIS/models/<nom>-mlx/{config.json, weights.safetensors}.
Har bir parametr nomi va o'lchami MLX modeli kutganiga solishtiriladi — birortasi mos kelmasa,
hech narsa saqlanmaydi.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import mlx.core as mx
from huggingface_hub import snapshot_download
from mlx.utils import tree_flatten
from mlx_whisper import whisper

MODELS_DIR = Path.home() / "Library" / "Application Support" / "JARVIS" / "models"

LAYER_PARTS = {
    "self_attn.q_proj": "attn.query",
    "self_attn.k_proj": "attn.key",
    "self_attn.v_proj": "attn.value",
    "self_attn.out_proj": "attn.out",
    "self_attn_layer_norm": "attn_ln",
    "encoder_attn.q_proj": "cross_attn.query",
    "encoder_attn.k_proj": "cross_attn.key",
    "encoder_attn.v_proj": "cross_attn.value",
    "encoder_attn.out_proj": "cross_attn.out",
    "encoder_attn_layer_norm": "cross_attn_ln",
    "fc1": "mlp1",
    "fc2": "mlp2",
    "final_layer_norm": "mlp_ln",
}
SIMPLE = {
    "model.encoder.conv1": "encoder.conv1",
    "model.encoder.conv2": "encoder.conv2",
    "model.encoder.layer_norm": "encoder.ln_post",
    "model.decoder.embed_tokens": "decoder.token_embedding",
    "model.decoder.layer_norm": "decoder.ln",
}
SKIP = ("model.encoder.embed_positions.", "proj_out.")  # MLX o'zi hisoblaydi / bog'langan


def map_name(hf: str) -> str | None:
    if hf.startswith(SKIP):
        return None
    if hf == "model.decoder.embed_positions.weight":
        return "decoder.positional_embedding"
    m = re.match(r"model\.(encoder|decoder)\.layers\.(\d+)\.(.+)\.(weight|bias)$", hf)
    if m:
        side, idx, part, kind = m.groups()
        if part not in LAYER_PARTS:
            raise KeyError(f"noma'lum qatlam qismi: {hf}")
        return f"{side}.blocks.{idx}.{LAYER_PARTS[part]}.{kind}"
    base, _, kind = hf.rpartition(".")
    if base in SIMPLE:
        return f"{SIMPLE[base]}.{kind}"
    raise KeyError(f"noma'lum parametr: {hf}")


def dims_from_config(c: dict) -> whisper.ModelDimensions:
    return whisper.ModelDimensions(
        n_mels=c["num_mel_bins"],
        n_audio_ctx=c["max_source_positions"],
        n_audio_state=c["d_model"],
        n_audio_head=c["encoder_attention_heads"],
        n_audio_layer=c["encoder_layers"],
        n_vocab=c["vocab_size"],
        n_text_ctx=c["max_target_positions"],
        n_text_state=c["d_model"],
        n_text_head=c["decoder_attention_heads"],
        n_text_layer=c["decoder_layers"],
    )


def convert(repo: str, out: Path, dtype=mx.float16) -> Path:
    src = Path(snapshot_download(repo, allow_patterns=["config.json", "*.safetensors"]))
    config = json.loads((src / "config.json").read_text())
    dims = dims_from_config(config)
    expected = dict(tree_flatten(whisper.Whisper(dims, dtype).parameters()))
    expected.pop("alignment_heads", None)  # MLX standart qiymatini ishlatadi

    hf = {}
    for f in sorted(src.glob("*.safetensors")):
        hf.update(mx.load(str(f)))

    weights: dict[str, mx.array] = {}
    for name, value in hf.items():
        target = map_name(name)
        if target is None:
            continue
        if target.endswith(("conv1.weight", "conv2.weight")):
            value = value.swapaxes(1, 2)  # torch (out, in, k) → mlx (out, k, in)
        if target not in expected:
            raise KeyError(f"MLX modelida bunday parametr yo'q: {target} ({name})")
        if tuple(value.shape) != tuple(expected[target].shape):
            raise ValueError(f"o'lcham mos emas: {target} {value.shape} ≠ {expected[target].shape}")
        weights[target] = value.astype(dtype)

    missing = sorted(set(expected) - set(weights))
    if missing:
        raise ValueError(f"{len(missing)} ta parametr topilmadi, masalan: {missing[:5]}")

    out.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(str(out / "weights.safetensors"), weights)
    config_out = {**dims.__dict__, "model_type": "whisper"}
    (out / "config.json").write_text(json.dumps(config_out, indent=2))
    (out / "SOURCE.txt").write_text(repo + "\n")  # config.json'da ortiqcha kalit bo'lmasligi kerak
    print(f"✅ {len(weights)} ta parametr o'girildi → {out}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("repo", nargs="?", default="qirol4006/Whisper-3-turbo-uzbek")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    out = a.out or MODELS_DIR / (a.repo.split("/")[-1].lower() + "-mlx")
    try:
        convert(a.repo, out)
    except (KeyError, ValueError) as e:
        sys.exit(f"❌ O'girib bo'lmadi: {e}")


if __name__ == "__main__":
    main()
