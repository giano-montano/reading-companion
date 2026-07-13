import json, sys
sys.stdout.reconfigure(encoding='utf-8')

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else 60

with open("data/outputs/retrieval/viaje_al_centro_de_la_tierra_julio_verne.retrieval.jsonl", encoding="utf-8") as f:
    chunks = [json.loads(line) for line in f]

for i in range(start-1, min(end, len(chunks))):
    c = chunks[i]
    print(f"=== CHUNK {i+1}/{len(chunks)} | {c['chunk_id']} ===")
    print(c['text'][:1200])
    print("---END---\n")
