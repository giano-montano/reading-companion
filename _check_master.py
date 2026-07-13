import json

data = json.loads(open("data/master/el_maravilloso_mago_de_oz_baum_lyman_frank.master.json", encoding="utf-8").read())
blocks = data["blocks"]
print(f"Total blocks: {len(blocks)}")

# Count types
from collections import Counter
types = Counter(b["type"] for b in blocks)
narr = Counter(b["is_narrative"] for b in blocks)
print(f"Types: {dict(types)}")
print(f"Narrative: {dict(narr)}")

# Show first 20 blocks
for b in blocks[:20]:
    text = b["text"][:80].replace("\n", " ")
    print(f"  {b['id_block']} type={b['type']} narr={b['is_narrative']} [{b['char_start']}-{b['char_end']}] {text}")
