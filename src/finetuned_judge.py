"""
Fine-tuned judge — replaces Laya's zero-shot answers for the 15 build-plan
questions with linear heads trained on ground-truth labels (see
scripts/train_finetune.py and models/finetune_v1/metadata.json).

Why this exists: Laya's zero-shot noul answers were measured to be
essentially non-discriminative (e.g. f_sonderumlage: Laya says "true" on
98.7% of 364 real listings; ground truth is 0.3%). This module is a drop-in
alternative to src.judge.run_judge with the same JudgeResult/Judgment shape,
so run_v1_pipeline.py can select it via --judge finetuned without touching
the original Laya path (kept intact for comparison / rollback).

Embedding: BAAI/bge-m3 (already cached locally), CLS-token pooling,
L2-normalized -- must match scripts/embed_listings.py exactly, since the
heads were trained on that embedding.

Coverage note: several noul questions had too few positive examples (<15) in
the label set to train a meaningful classifier and fall back to predicting
the majority class (see metadata.json's "majority_fallback" flag per
question) -- this is an honest gap, not a hidden one; revisit once more
labels exist.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import torch
import torch.nn as nn

from src.judge import Judgment, JudgeResult, QUESTION_DEFS

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "models" / "finetune_v1"
HEADS_PATH = MODEL_DIR / "heads.pt"
META_PATH = MODEL_DIR / "metadata.json"

_state: dict[str, Any] = {}  # lazy-loaded cache: tokenizer, embed model, heads, metadata


def _load() -> None:
    if _state:
        return
    # NOTE: deliberately does NOT call _ensure_hf_home() -- that redirects HF_HOME to an
    # empty project-local cache dir (a workaround for Laya's own sandboxed downloads in
    # src/judge.py) which breaks finding BAAI/bge-m3 in its real cache at
    # ~/.cache/huggingface. scripts/embed_listings.py (used for training) never touches
    # HF_HOME either, for the same reason -- keep both consistent.
    from transformers import AutoTokenizer, AutoModel

    with open(META_PATH) as f:
        meta = json.load(f)
    heads_state = torch.load(HEADS_PATH, map_location="cpu", weights_only=True)

    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", local_files_only=True)
    embed_model = AutoModel.from_pretrained("BAAI/bge-m3", local_files_only=True)
    embed_model.eval()

    heads: dict[str, nn.Module] = {}
    for qid, qmeta in meta.items():
        if qmeta.get("majority_fallback"):
            continue
        qtype = qmeta["type"]
        if qtype == "noul":
            head = nn.Linear(1024, 1)
        elif qtype == "choice":
            head = nn.Linear(1024, len(qmeta["criteria"]))
        elif qtype == "score":
            head = nn.Linear(1024, 1)
        else:
            continue
        head.load_state_dict(heads_state[qid])
        head.eval()
        heads[qid] = head

    _state["tok"] = tok
    _state["embed_model"] = embed_model
    _state["heads"] = heads
    _state["meta"] = meta
    logger.info("finetuned_judge loaded: %d trained heads, %d majority-fallback questions",
                len(heads), sum(1 for m in meta.values() if m.get("majority_fallback")))


def _embed(text: str) -> torch.Tensor:
    tok = _state["tok"]
    model = _state["embed_model"]
    enc = tok([text[:4000]], padding=True, truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        out = model(**enc)
        cls = out.last_hidden_state[:, 0]
        cls = torch.nn.functional.normalize(cls, p=2, dim=1)
    return cls  # shape (1, 1024)


def run_judge_finetuned(
    text: str,
    questions: Optional[dict[str, dict[str, Any]]] = None,
) -> JudgeResult:
    """Drop-in alternative to src.judge.run_judge, same JudgeResult shape."""
    start = time.time()
    result = JudgeResult(listing_id="")

    if questions is None:
        questions = dict(QUESTION_DEFS)

    try:
        _load()
    except Exception as e:
        result.errors.append(f"finetuned_judge load failed: {e}")
        logger.error("finetuned_judge load failed: %s", e)
        for qid in questions:
            result.judgments.append(Judgment(listing_id="", question_id=qid, answer=None))
        result.execution_time_ms = (time.time() - start) * 1000
        return result

    emb = _embed(text)
    meta = _state["meta"]
    heads = _state["heads"]

    for qid, qdef in questions.items():
        qmeta = meta.get(qid)
        if qmeta is None:
            result.judgments.append(Judgment(listing_id="", question_id=qid, answer=None))
            continue

        if qmeta.get("majority_fallback"):
            result.judgments.append(Judgment(
                listing_id="", question_id=qid,
                model_version="finetuned-v1",
                answer=qmeta["fallback_value"],
                probability=None,
                confidence=None,
            ))
            continue

        head = heads[qid]
        qtype = qmeta["type"]
        with torch.no_grad():
            logits = head(emb).squeeze(0)

        if qtype == "noul":
            prob_true = torch.sigmoid(logits).item()
            answer = "true" if prob_true > 0.5 else "false"
            confidence = prob_true if answer == "true" else (1 - prob_true)
            result.judgments.append(Judgment(
                listing_id="", question_id=qid, model_version="finetuned-v1",
                answer=answer, probability=prob_true, confidence=confidence,
            ))
        elif qtype == "choice":
            probs = torch.softmax(logits, dim=0)
            idx = int(probs.argmax().item())
            criteria = qmeta["criteria"]
            result.judgments.append(Judgment(
                listing_id="", question_id=qid, model_version="finetuned-v1",
                answer=criteria[idx], probability=probs[idx].item(), confidence=probs[idx].item(),
            ))
        elif qtype == "score":
            criteria = qmeta["criteria"]
            val = logits.item()
            idx = max(0, min(len(criteria) - 1, round(val)))
            result.judgments.append(Judgment(
                listing_id="", question_id=qid, model_version="finetuned-v1",
                answer=criteria[idx], probability=None, confidence=None,
            ))
        else:
            result.judgments.append(Judgment(listing_id="", question_id=qid, answer=None))

    result.execution_time_ms = (time.time() - start) * 1000
    return result
