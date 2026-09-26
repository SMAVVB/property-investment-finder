"""Compute BGE-M3 sentence embeddings for all labeled listings' raw_data.
Cached to models/finetune_v1/embeddings.npz (listing_ids + vectors).
"""
import sqlite3
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

DB = "/tmp/property-investment-finder/data/listings.db"
OUT = "/tmp/property-investment-finder/models/finetune_v1/embeddings.npz"

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("select distinct listing_id from labels")
    labeled_ids = sorted(r[0] for r in cur.fetchall())
    print(f"{len(labeled_ids)} labeled listings")

    texts = {}
    for lid in labeled_ids:
        cur.execute("select raw_data from listing where listing_id=?", (lid,))
        row = cur.fetchone()
        texts[lid] = row[0] if row and row[0] else ""

    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", local_files_only=True)
    model = AutoModel.from_pretrained("BAAI/bge-m3", local_files_only=True)
    model.eval()

    ids_out = []
    vecs_out = []
    BATCH = 16
    ids_list = list(labeled_ids)
    with torch.no_grad():
        for i in range(0, len(ids_list), BATCH):
            batch_ids = ids_list[i:i+BATCH]
            batch_texts = [texts[x][:4000] for x in batch_ids]
            enc = tok(batch_texts, padding=True, truncation=True, max_length=512, return_tensors="pt")
            out = model(**enc)
            cls = out.last_hidden_state[:, 0]  # BGE uses CLS pooling for dense embeddings
            cls = torch.nn.functional.normalize(cls, p=2, dim=1)
            ids_out.extend(batch_ids)
            vecs_out.append(cls.numpy())
            print(f"  embedded {i+len(batch_ids)}/{len(ids_list)}")

    vecs = np.concatenate(vecs_out, axis=0)
    np.savez(OUT, ids=np.array(ids_out), vecs=vecs)
    print("saved", OUT, vecs.shape)

if __name__ == "__main__":
    main()
