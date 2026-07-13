import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open("data/outputs/retrieval/viaje_al_centro_de_la_tierra_julio_verne.retrieval.jsonl", encoding="utf-8") as f:
    chunks = [json.loads(line) for line in f]

for i, c in enumerate(chunks):
    print(f"CHUNK {i+1}|{c['chunk_id']}|{c['text'][:150]}")

print(f"TOTAL: {len(chunks)}")
