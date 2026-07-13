import sys
sys.path.insert(0, 'src')
from companion.providers.factory import get_router_llm, get_content_llm
import time

# Test router
print("Testing router LLM (8B)...", flush=True)
router = get_router_llm()
t0 = time.time()
r = router.chat([
    {"role": "system", "content": "Responde solo con JSON."},
    {"role": "user", "content": 'Di hola en JSON: {"saludo": "hola"}. SOLO el JSON, nada más.'},
])
print(f"Router response ({time.time()-t0:.1f}s): {r[:200]}", flush=True)
print("---", flush=True)

# Test content
print("Testing content LLM (70B)...", flush=True)
content = get_content_llm()
t0 = time.time()
r = content.chat([
    {"role": "system", "content": "Responde solo con JSON."},
    {"role": "user", "content": 'Di hola en JSON: {"saludo": "hola"}. SOLO el JSON, nada más.'},
])
print(f"Content response ({time.time()-t0:.1f}s): {r[:200]}", flush=True)
