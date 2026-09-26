"""Train per-question classifier/regressor heads on top of frozen BGE-M3
embeddings, using ground-truth labels from data/listings.db's `labels` table.

Replaces Laya's zero-shot noul answers, which were shown to be essentially
non-discriminative (e.g. f_sonderumlage: Laya says true 98.7% of the time,
ground truth is 0.3%).

Outputs models/finetune_v1/heads.pt (state dicts) and
models/finetune_v1/metadata.json (per-question: type, criteria order,
majority_fallback bool + value, held-out metrics).
"""
import json
import random
import sqlite3
import numpy as np
import torch
import torch.nn as nn

DB = "/tmp/property-investment-finder/data/listings.db"
EMB = "/tmp/property-investment-finder/models/finetune_v1/embeddings.npz"
OUT_HEADS = "/tmp/property-investment-finder/models/finetune_v1/heads.pt"
OUT_META = "/tmp/property-investment-finder/models/finetune_v1/metadata.json"

NOUL_QUESTIONS = ["f_sonderumlage", "f_milieuschutz", "f_erbpacht", "f_staffelmiete",
                  "f_renovation", "f_heating_fossil", "f_small_weg", "f_tenant_issue", "f_wg_layout"]
CHOICE_QUESTIONS = {
    "c_tenant_type": ["student", "single", "couple", "family"],
    "c_letting_status": ["let", "vacant", "owner-occupied", "unclear"],
}
SCORE_QUESTIONS = {
    "s_condition": ["Sehr schlecht", "Schlecht", "Durchschnittlich", "Gut", "Sehr gut"],
    "s_building": ["Sehr schlecht", "Schlecht", "Durchschnittlich", "Gut", "Sehr gut"],
    "s_micro_location": ["Sehr schlecht", "Schlecht", "Durchschnittlich", "Gut", "Sehr gut"],
    "s_description_trust": ["Sehr unglaubwürdig", "Unglaubwürdig", "Durchschnittlich", "Glaubwürdig", "Sehr glaubwürdig"],
}

MIN_POSITIVES_FOR_TRAINING = 15
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


def load_embeddings():
    data = np.load(EMB, allow_pickle=True)
    ids = data["ids"]
    vecs = data["vecs"].astype(np.float32)
    return {lid: vecs[i] for i, lid in enumerate(ids)}


def load_labels(question_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("select listing_id, label_value from labels where label_key=?", (question_id,))
    return dict(cur.fetchall())


def stratified_split(labels_by_class, test_frac=0.2):
    """labels_by_class: {class_idx: [listing_id,...]}. Returns (train_ids, test_ids)."""
    train_ids, test_ids = [], []
    for cls, ids in labels_by_class.items():
        ids = list(ids)
        random.shuffle(ids)
        n_test = max(1, round(len(ids) * test_frac)) if len(ids) >= 2 else 0
        test_ids.extend(ids[:n_test])
        train_ids.extend(ids[n_test:])
    return train_ids, test_ids


def prf(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def train_binary(embs, labels, question_id, meta):
    ids = [i for i in labels if i in embs]
    y = {i: (1 if labels[i] == "true" else 0) for i in ids}
    n_pos = sum(y.values())
    n_neg = len(ids) - n_pos
    if n_pos < MIN_POSITIVES_FOR_TRAINING:
        majority = "false" if n_neg >= n_pos else "true"
        meta[question_id] = {
            "type": "noul", "majority_fallback": True, "fallback_value": majority,
            "n_examples": len(ids), "n_positive": n_pos,
            "note": f"only {n_pos}/{len(ids)} positive examples, below the {MIN_POSITIVES_FOR_TRAINING}-positive "
                    f"training threshold; predicting majority class ('{majority}') until more labels exist.",
        }
        print(f"  [{question_id}] SKIP training (n_pos={n_pos}) -> majority fallback '{majority}'")
        return None

    by_class = {0: [i for i in ids if y[i] == 0], 1: [i for i in ids if y[i] == 1]}
    train_ids, test_ids = stratified_split(by_class)
    Xtr = torch.tensor(np.stack([embs[i] for i in train_ids]))
    ytr = torch.tensor([y[i] for i in train_ids], dtype=torch.float32)
    Xte = torch.tensor(np.stack([embs[i] for i in test_ids]))
    yte = torch.tensor([y[i] for i in test_ids], dtype=torch.float32)

    n_tr_pos = ytr.sum().item()
    n_tr_neg = len(ytr) - n_tr_pos
    pos_weight = torch.tensor([n_tr_neg / max(n_tr_pos, 1)])

    head = nn.Linear(1024, 1)
    opt = torch.optim.Adam(head.parameters(), lr=1e-2, weight_decay=1e-2)
    lossf = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    for epoch in range(300):
        opt.zero_grad()
        logits = head(Xtr).squeeze(-1)
        loss = lossf(logits, ytr)
        loss.backward()
        opt.step()

    with torch.no_grad():
        pred = (torch.sigmoid(head(Xte).squeeze(-1)) > 0.5).float()
    tp = ((pred == 1) & (yte == 1)).sum().item()
    fp = ((pred == 1) & (yte == 0)).sum().item()
    fn = ((pred == 0) & (yte == 1)).sum().item()
    tn = ((pred == 0) & (yte == 0)).sum().item()
    precision, recall, f1 = prf(tp, fp, fn)
    acc = (tp + tn) / len(yte) if len(yte) else 0.0
    meta[question_id] = {
        "type": "noul", "majority_fallback": False,
        "n_examples": len(ids), "n_positive": n_pos, "n_train": len(train_ids), "n_test": len(test_ids),
        "held_out": {"precision": round(precision, 3), "recall": round(recall, 3),
                     "f1": round(f1, 3), "accuracy": round(acc, 3), "tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }
    print(f"  [{question_id}] TRAINED n_train={len(train_ids)} n_test={len(test_ids)} "
          f"P={precision:.2f} R={recall:.2f} F1={f1:.2f} acc={acc:.2f}")
    return head


def train_multiclass(embs, labels, question_id, criteria, meta):
    ids = [i for i in labels if i in embs and labels[i] in criteria]
    cls_of = {i: criteria.index(labels[i]) for i in ids}
    by_class = {}
    for i in ids:
        by_class.setdefault(cls_of[i], []).append(i)
    counts = {criteria[k]: len(v) for k, v in by_class.items()}
    train_ids, test_ids = stratified_split(by_class)
    Xtr = torch.tensor(np.stack([embs[i] for i in train_ids]))
    ytr = torch.tensor([cls_of[i] for i in train_ids], dtype=torch.long)
    Xte = torch.tensor(np.stack([embs[i] for i in test_ids])) if test_ids else None
    yte = torch.tensor([cls_of[i] for i in test_ids], dtype=torch.long) if test_ids else None

    K = len(criteria)
    head = nn.Linear(1024, K)
    opt = torch.optim.Adam(head.parameters(), lr=1e-2, weight_decay=1e-2)
    lossf = nn.CrossEntropyLoss()
    for epoch in range(300):
        opt.zero_grad()
        logits = head(Xtr)
        loss = lossf(logits, ytr)
        loss.backward()
        opt.step()

    per_class = {}
    if Xte is not None and len(test_ids):
        with torch.no_grad():
            pred = head(Xte).argmax(dim=1)
        acc = (pred == yte).float().mean().item()
        for k, name in enumerate(criteria):
            tp = ((pred == k) & (yte == k)).sum().item()
            fp = ((pred == k) & (yte != k)).sum().item()
            fn = ((pred != k) & (yte == k)).sum().item()
            precision, recall, f1 = prf(tp, fp, fn)
            per_class[name] = {"precision": round(precision, 3), "recall": round(recall, 3),
                                "f1": round(f1, 3), "support": int((yte == k).sum().item())}
    else:
        acc = None

    meta[question_id] = {
        "type": "choice", "criteria": criteria, "class_counts": counts,
        "n_examples": len(ids), "n_train": len(train_ids), "n_test": len(test_ids),
        "held_out_accuracy": round(acc, 3) if acc is not None else None,
        "held_out_per_class": per_class,
    }
    print(f"  [{question_id}] TRAINED (multiclass) n_train={len(train_ids)} n_test={len(test_ids)} acc={acc}")
    return head


def train_ordinal(embs, labels, question_id, criteria, meta):
    ids = [i for i in labels if i in embs and labels[i] in criteria]
    val_of = {i: float(criteria.index(labels[i])) for i in ids}
    by_class = {}
    for i in ids:
        by_class.setdefault(int(val_of[i]), []).append(i)
    train_ids, test_ids = stratified_split(by_class)
    Xtr = torch.tensor(np.stack([embs[i] for i in train_ids]))
    ytr = torch.tensor([val_of[i] for i in train_ids], dtype=torch.float32)
    Xte = torch.tensor(np.stack([embs[i] for i in test_ids])) if test_ids else None
    yte = torch.tensor([val_of[i] for i in test_ids], dtype=torch.float32) if test_ids else None

    head = nn.Linear(1024, 1)
    opt = torch.optim.Adam(head.parameters(), lr=1e-2, weight_decay=1e-2)
    lossf = nn.MSELoss()
    for epoch in range(300):
        opt.zero_grad()
        pred = head(Xtr).squeeze(-1)
        loss = lossf(pred, ytr)
        loss.backward()
        opt.step()

    if Xte is not None and len(test_ids):
        with torch.no_grad():
            pred = head(Xte).squeeze(-1).clamp(0, len(criteria) - 1)
        mae = (pred - yte).abs().mean().item()
        rounded = pred.round()
        exact_acc = (rounded == yte).float().mean().item()
        within_one = ((pred - yte).abs() <= 1.0).float().mean().item()
    else:
        mae = exact_acc = within_one = None

    counts = {criteria[k]: len(v) for k, v in by_class.items()}
    meta[question_id] = {
        "type": "score", "criteria": criteria, "class_counts": counts,
        "n_examples": len(ids), "n_train": len(train_ids), "n_test": len(test_ids),
        "held_out": {"mae": round(mae, 3) if mae is not None else None,
                     "exact_accuracy": round(exact_acc, 3) if exact_acc is not None else None,
                     "within_one_class_accuracy": round(within_one, 3) if within_one is not None else None},
    }
    print(f"  [{question_id}] TRAINED (ordinal) n_train={len(train_ids)} n_test={len(test_ids)} "
          f"MAE={mae} exact_acc={exact_acc} within1={within_one}")
    return head


def main():
    embs = load_embeddings()
    print(f"loaded {len(embs)} embeddings")

    meta = {}
    heads = {}

    for q in NOUL_QUESTIONS:
        labels = load_labels(q)
        head = train_binary(embs, labels, q, meta)
        if head is not None:
            heads[q] = head.state_dict()

    for q, criteria in CHOICE_QUESTIONS.items():
        labels = load_labels(q)
        head = train_multiclass(embs, labels, q, criteria, meta)
        heads[q] = head.state_dict()

    for q, criteria in SCORE_QUESTIONS.items():
        labels = load_labels(q)
        head = train_ordinal(embs, labels, q, criteria, meta)
        heads[q] = head.state_dict()

    torch.save(heads, OUT_HEADS)
    with open(OUT_META, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print("saved", OUT_HEADS, OUT_META)


if __name__ == "__main__":
    main()
