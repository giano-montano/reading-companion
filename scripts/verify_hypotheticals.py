"""Verify hypotheticals output."""
import json

with open("data/outputs/hypotheticals/el_viejo_y_el_mar_ernest_hemingway.hypotheticals.jsonl", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total de lineas: {len(lines)}")

errors = []
for i, line in enumerate(lines, 1):
    obj = json.loads(line)
    n = len(obj["hypothetical_questions"])
    if n != 5:
        errors.append(f"Chunk {i} tiene {n} preguntas")

if errors:
    for e in errors:
        print(f"ERROR: {e}")
else:
    print("Todos los 139 chunks tienen exactamente 5 preguntas.")

# Show samples
obj1 = json.loads(lines[0])
print("\n--- Muestra 1 (chunk 1) ---")
for j, q in enumerate(obj1["hypothetical_questions"], 1):
    print(f"  {j}. {q}")

obj50 = json.loads(lines[49])
print("\n--- Muestra 2 (chunk 50) ---")
for j, q in enumerate(obj50["hypothetical_questions"], 1):
    print(f"  {j}. {q}")

obj139 = json.loads(lines[138])
print("\n--- Muestra 3 (chunk 139) ---")
for j, q in enumerate(obj139["hypothetical_questions"], 1):
    print(f"  {j}. {q}")
