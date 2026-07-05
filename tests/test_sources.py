#!/usr/bin/env python3
"""Smoke test for minion's multi-source system. No live server needed."""
import os, sys, importlib

# Add project root (parent of this tests/ dir) to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def clear_minion_env():
    for k in list(os.environ):
        if k.startswith("MINION_"):
            del os.environ[k]
    # Scrub the built-in sources' trigger keys so tests that want a known,
    # minimal source set aren't perturbed by a real ~/.env / shell export of
    # TOGETHER_API_KEY / OPENROUTER_API_KEY. (Tests that exercise a built-in
    # source set it explicitly.)
    os.environ.pop("TOGETHER_API_KEY", None)
    os.environ.pop("OPENROUTER_API_KEY", None)
    # Prevent ~/.env from leaking real config into the tests. _load_env_file()
    # re-reads it on every reload, so point it at a nonexistent file.
    os.environ["MINION_ENV_FILE"] = "/dev/null"

# --- Test 1: legacy fallback (no MINION_SOURCE_* vars) ---
clear_minion_env()
sys.argv = ["minion.py"]
import minion
importlib.reload(minion)
print("TEST 1: legacy fallback")
print(f"  SOURCES: {list(minion.SOURCES.keys())}")
print(f"  ACTIVE.name: {minion.ACTIVE.name}")
print(f"  client.base_url: {minion.client.base_url}")
assert list(minion.SOURCES.keys()) == ["local"]
assert minion.ACTIVE.name == "local"
print("  PASS\n")

# --- Test 2: multi-source discovery ---
clear_minion_env()
os.environ["MINION_SOURCES"] = "local,zai"
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["MINION_SOURCE_LOCAL_API_KEY"] = "sk-noop"
os.environ["ZAI_TEST_KEY"] = "fake-zai-key-12345"
os.environ["MINION_SOURCE_ZAI_BASE_URL"] = "https://api.z.ai/api/paas/v4"
os.environ["MINION_SOURCE_ZAI_API_KEY"] = "$ZAI_TEST_KEY"
os.environ["MINION_SOURCE_ZAI_MODEL"] = "glm-x-preview"
sys.argv = ["minion.py"]
importlib.reload(minion)
print("TEST 2: multi-source discovery")
print(f"  SOURCE_ORDER: {minion.SOURCE_ORDER}")
print(f"  ACTIVE.name: {minion.ACTIVE.name}")
print(f"  zai.api_key: {minion.SOURCES['zai'].api_key}")
print(f"  zai.model: {minion.SOURCES['zai'].model}")
print(f"  local.model: {minion.SOURCES['local'].model}")
assert minion.SOURCE_ORDER == ["local", "zai"]
assert minion.ACTIVE.name == "local"
assert minion.SOURCES["zai"].api_key == "fake-zai-key-12345", "$indirection failed"
assert minion.SOURCES["zai"].model == "glm-x-preview"
print("  PASS\n")

# --- Test 3: switch_source ---
print("TEST 3: switch_source('zai')")
old_client_id = id(minion.client)
old_model = minion.MODEL
minion.switch_source("zai")
print(f"  ACTIVE.name: {minion.ACTIVE.name}")
print(f"  MODEL: {minion.MODEL}")
print(f"  client.base_url: {minion.client.base_url}")
assert minion.ACTIVE.name == "zai"
assert minion.MODEL == "glm-x-preview"
assert id(minion.client) != old_client_id, "client object should have changed"
print("  PASS\n")

# --- Test 4: switch back ---
minion.switch_source("local")
print("TEST 4: switch back to local")
assert minion.ACTIVE.name == "local"
print("  PASS\n")

# --- Test 5: unknown source ---
print("TEST 5: unknown source")
result = minion.switch_source("nonexistent")
assert result is False
print("  PASS\n")

# --- Test 6: --source flag ---
clear_minion_env()
os.environ["MINION_SOURCES"] = "local,zai"
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["MINION_SOURCE_ZAI_BASE_URL"] = "https://api.z.ai/api/paas/v4"
os.environ["MINION_SOURCE_ZAI_MODEL"] = "glm-x-preview"
sys.argv = ["minion.py", "--source", "zai"]
importlib.reload(minion)
print("TEST 6: --source zai flag")
print(f"  ACTIVE.name: {minion.ACTIVE.name}")
assert minion.ACTIVE.name == "zai"
print("  PASS\n")

# --- Test 7: auto-discover without MINION_SOURCES ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["MINION_SOURCE_ZAI_BASE_URL"] = "https://api.z.ai/api/paas/v4"
importlib.reload(minion)
print("TEST 7: auto-discover from BASE_URL vars")
print(f"  SOURCE_ORDER: {minion.SOURCE_ORDER}")
assert set(minion.SOURCE_ORDER) == {"local", "zai"}
print("  PASS\n")

# --- Test 8: _banner() reflects active source ---
minion.switch_source("zai")
banner = minion._banner()
print("TEST 8: _banner() with multiple sources")
print(f"  banner: {banner}")
assert "zai" in banner
print("  PASS\n")

# --- Test 9: built-in `together` source auto-registers with a key ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["TOGETHER_API_KEY"] = "fake-together-key"
importlib.reload(minion)
print("TEST 9: built-in together source auto-register")
print(f"  SOURCE_ORDER: {minion.SOURCE_ORDER}")
print(f"  together.base_url: {minion.SOURCES['together'].base_url}")
print(f"  together.model: {minion.SOURCES['together'].model}")
print(f"  together.api_key: {minion.SOURCES['together'].api_key}")
assert "together" in minion.SOURCES, "together source should auto-register with a key"
assert minion.SOURCES["together"].base_url == "https://api.together.xyz/v1"
assert minion.SOURCES["together"].model == "zai-org/GLM-5.2", "default model should be GLM-5.2"
assert minion.SOURCES["together"].api_key == "fake-together-key"
# Registered last, so the first-defined source stays the startup default.
assert minion.SOURCE_ORDER[0] == "local"
assert minion.SOURCE_ORDER[-1] == "together"
assert minion.ACTIVE.name == "local", "local should remain the default on load"
print("  PASS\n")

# --- Test 10: no together source without a key ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
importlib.reload(minion)
print("TEST 10: no together source without TOGETHER_API_KEY")
print(f"  SOURCE_ORDER: {minion.SOURCE_ORDER}")
assert "together" not in minion.SOURCES, "no together source without a key"
print("  PASS\n")

# --- Test 11: explicit together config wins over the built-in ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCES"] = "together"
os.environ["MINION_SOURCE_TOGETHER_BASE_URL"] = "https://my-proxy.example/v1"
os.environ["MINION_SOURCE_TOGETHER_API_KEY"] = "custom-key"
os.environ["MINION_SOURCE_TOGETHER_MODEL"] = "my-org/my-model"
os.environ["TOGETHER_API_KEY"] = "fake-together-key"
importlib.reload(minion)
print("TEST 11: explicit together config overrides built-in")
print(f"  together.base_url: {minion.SOURCES['together'].base_url}")
print(f"  together.model: {minion.SOURCES['together'].model}")
assert minion.SOURCES["together"].base_url == "https://my-proxy.example/v1"
assert minion.SOURCES["together"].model == "my-org/my-model"
assert minion.SOURCES["together"].api_key == "custom-key"
print("  PASS\n")

# --- Test 12: switch_source model override (per-switch model pin) ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCES"] = "together"
os.environ["MINION_SOURCE_TOGETHER_BASE_URL"] = "https://api.together.xyz/v1"
os.environ["MINION_SOURCE_TOGETHER_API_KEY"] = "k"
os.environ["MINION_SOURCE_TOGETHER_MODEL"] = "zai-org/GLM-5.2"
importlib.reload(minion)
print("TEST 12: switch_source model_override")
minion.switch_source("together")
assert minion.MODEL == "zai-org/GLM-5.2", "bare switch → source default"
# Override pins a different model for this switch.
minion.switch_source("together", model_override="zai-org/GLM-4.6")
assert minion.MODEL == "zai-org/GLM-4.6", "override should pin MODEL"
# A bare switch afterward falls back to the configured default (non-sticky).
minion.switch_source("together")
assert minion.MODEL == "zai-org/GLM-5.2", "bare switch should restore default"
print("  PASS\n")

# --- Test 13: built-in `openrouter` source auto-registers with a key ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["OPENROUTER_API_KEY"] = "fake-or-key"
importlib.reload(minion)
print("TEST 13: built-in openrouter source auto-register")
print(f"  SOURCE_ORDER: {minion.SOURCE_ORDER}")
or_src = minion.SOURCES.get("openrouter")
assert or_src is not None, "openrouter source should auto-register with a key"
assert or_src.base_url == "https://openrouter.ai/api/v1"
assert or_src.model == "z-ai/glm-5.2", "default model should be z-ai/glm-5.2"
assert or_src.api_key == "fake-or-key"
# Default routing pins parasail/fp8 with no fallback.
assert or_src.extra_body == {"provider": {"order": ["parasail/fp8"],
                                          "allow_fallbacks": False}}, \
    f"default routing should pin parasail/fp8, got {or_src.extra_body!r}"
# Registered last, so the first-defined source stays the startup default.
assert minion.SOURCE_ORDER[0] == "local"
assert minion.SOURCE_ORDER[-1] == "openrouter"
assert minion.ACTIVE.name == "local", "local should remain the default on load"
print("  PASS\n")

# --- Test 14: no openrouter source without a key ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
importlib.reload(minion)
print("TEST 14: no openrouter source without OPENROUTER_API_KEY")
print(f"  SOURCE_ORDER: {minion.SOURCE_ORDER}")
assert "openrouter" not in minion.SOURCES, "no openrouter source without a key"
print("  PASS\n")

# --- Test 15: explicit openrouter config overrides the built-in ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCES"] = "openrouter"
os.environ["MINION_SOURCE_OPENROUTER_BASE_URL"] = "https://my-or-proxy.example/v1"
os.environ["MINION_SOURCE_OPENROUTER_API_KEY"] = "custom-or-key"
os.environ["MINION_SOURCE_OPENROUTER_MODEL"] = "my-org/my-model"
os.environ["MINION_SOURCE_OPENROUTER_EXTRA_BODY"] = (
    '{"provider":{"order":["Together"],"allow_fallbacks":true}}')
os.environ["OPENROUTER_API_KEY"] = "fake-or-key"
importlib.reload(minion)
print("TEST 15: explicit openrouter config overrides built-in")
print(f"  or.base_url: {minion.SOURCES['openrouter'].base_url}")
print(f"  or.model: {minion.SOURCES['openrouter'].model}")
assert minion.SOURCES["openrouter"].base_url == "https://my-or-proxy.example/v1"
assert minion.SOURCES["openrouter"].model == "my-org/my-model"
assert minion.SOURCES["openrouter"].api_key == "custom-or-key"
assert minion.SOURCES["openrouter"].extra_body == \
    {"provider": {"order": ["Together"], "allow_fallbacks": True}}
print("  PASS\n")

# --- Test 16: bad EXTRA_BODY JSON is ignored loudly (no silent routing) ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCES"] = "openrouter"
os.environ["MINION_SOURCE_OPENROUTER_BASE_URL"] = "https://openrouter.ai/api/v1"
os.environ["MINION_SOURCE_OPENROUTER_API_KEY"] = "k"
os.environ["MINION_SOURCE_OPENROUTER_MODEL"] = "z-ai/glm-5.2"
os.environ["MINION_SOURCE_OPENROUTER_EXTRA_BODY"] = "not json{"
importlib.reload(minion)
print("TEST 16: bad EXTRA_BODY JSON ignored")
# Built-in default routing does NOT fill in for a malformed explicit config —
# a typo must fail loudly (stderr warning) rather than silently route to the
# default, so extra_body stays None.
assert minion.SOURCES["openrouter"].extra_body is None, \
    "malformed EXTRA_BODY should yield no routing, not the built-in default"
print("  PASS\n")

# --- Test 17: _set_provider_order / _provider_order helpers ---
clear_minion_env()
sys.argv = ["minion.py"]
# Auto-register the built-in openrouter source (the path that seeds the
# parasail/fp8 default routing). An explicit MINION_SOURCES=openrouter without
# EXTRA_BODY would NOT inject the default — explicit config means user-control.
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["OPENROUTER_API_KEY"] = "k"
importlib.reload(minion)
print("TEST 17: _set_provider_order / _provider_order")
src = minion.SOURCES["openrouter"]
# Starts with the built-in default routing.
assert minion._provider_order(src) == ["parasail/fp8"]
# Pin a new ordered list — defaults to no fallback (deliberate choice).
minion._set_provider_order(src, ["Together", "DeepInfra"])
assert minion._provider_order(src) == ["Together", "DeepInfra"]
assert src.extra_body["provider"]["allow_fallbacks"] is False
# Explicit allow_fallbacks=True is honored.
minion._set_provider_order(src, ["Together"], allow_fallbacks=True)
assert src.extra_body["provider"]["allow_fallbacks"] is True
# Empty order clears routing entirely.
minion._set_provider_order(src, [])
assert minion._provider_order(src) == []
assert src.extra_body is None
print("  PASS\n")

# --- Test 18: extra_request_kwargs plumbing ---
clear_minion_env()
sys.argv = ["minion.py"]
os.environ["MINION_SOURCE_LOCAL_BASE_URL"] = "http://localhost:8080/v1"
os.environ["OPENROUTER_API_KEY"] = "k"
importlib.reload(minion)
print("TEST 18: extra_request_kwargs plumbing")
src = minion.SOURCES["openrouter"]
# Routed source yields an extra_body kwarg.
kw = src.extra_request_kwargs()
assert kw == {"extra_body": {"provider": {"order": ["parasail/fp8"],
                                          "allow_fallbacks": False}}}, kw
# Clearing routing yields nothing — non-routing sources contribute no kwarg.
minion._set_provider_order(src, [])
assert src.extra_request_kwargs() == {}
# Re-pin and confirm the active source's kwarg matches.
minion._set_provider_order(src, ["parasail/fp8"])
minion.switch_source("openrouter")
assert minion.ACTIVE.extra_request_kwargs() == \
    {"extra_body": {"provider": {"order": ["parasail/fp8"],
                                 "allow_fallbacks": False}}}
print("  PASS\n")

print("=" * 50)
print("ALL TESTS PASSED")
