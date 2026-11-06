"""
Local AI Service Status Detector.
Monitors connections to:
  1. Bionic / LM Studio (port 1234)
  2. Ollama (port 11434)
Provides real-time connection status, model names, and latency for UI presentation.
"""
import urllib.request
import json
import time


def check_bionic_status(host: str = "127.0.0.1", port: int = 1234, timeout: float = 1.5) -> dict:
    url = f"http://{host}:{port}/v1/models"
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id", "") for m in data.get("data", [])]
            primary = models[0] if models else "Active"
            # Extract clean short model name
            short_name = primary.split("/")[-1].split(":")[0]
            if len(short_name) > 24:
                short_name = short_name[:21] + "..."
            return {
                "online": True,
                "service": "Bionic",
                "model_id": primary,
                "display_name": f"Bionic ({short_name})",
                "latency_ms": round((time.time() - t0) * 1000),
                "port": port,
            }
    except Exception:
        return {"online": False, "service": "Bionic", "port": port}


def check_ollama_status(host: str = "127.0.0.1", port: int = 11434, timeout: float = 1.5) -> dict:
    url = f"http://{host}:{port}/api/tags"
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            primary = models[0] if models else "Active"
            return {
                "online": True,
                "service": "Ollama",
                "model_id": primary,
                "display_name": f"Ollama ({primary})",
                "latency_ms": round((time.time() - t0) * 1000),
                "port": port,
            }
    except Exception:
        return {"online": False, "service": "Ollama", "port": port}


def get_ai_connection_summary() -> dict:
    """Returns aggregated connection info for display in the UI."""
    bionic = check_bionic_status()
    ollama = check_ollama_status()

    services_online = []
    if bionic.get("online"):
        services_online.append(bionic["display_name"])
    if ollama.get("online"):
        services_online.append(ollama["display_name"])

    if services_online:
        summary_text = "🟢 AI: " + " + ".join(services_online)
        is_connected = True
    else:
        summary_text = "🔴 AI Offline (Start Bionic on :1234 or Ollama on :11434)"
        is_connected = False

    return {
        "connected": is_connected,
        "summary": summary_text,
        "bionic": bionic,
        "ollama": ollama,
    }
