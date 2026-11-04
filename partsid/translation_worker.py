"""Text-only translation in the existing isolated MLX environment."""
import json
import sys
import time
from pathlib import Path

from translation import make_entry, valid_entry


def main():
    import mlx.core as mx
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    request_path, response_path = map(Path, sys.argv[1:3])
    config = json.loads(request_path.read_text())
    mx.random.seed(0)
    old = json.loads(response_path.read_text()) if response_path.exists() else {}
    responses = {e["key"]: e for e in old.get("responses", []) if valid_entry(e)}
    rejections = []
    model, processor = None, None
    for i, request in enumerate(config["requests"]):
        if request["key"] in responses and responses[request["key"]]["prompt_sha256"] == request["prompt_sha256"]:
            print(f"Translation {i+1}/{len(config['requests'])}: cached", flush=True)
            continue
        if model is None:
            model, processor = load(config["model"], revision=config["revision"], trust_remote_code=False)
        prompt = apply_chat_template(processor, model.config, request["prompt"], num_images=0)
        started = time.perf_counter()
        result = generate(model, processor, prompt, max_tokens=config["max_tokens"], temperature=0.0, verbose=False)
        try:
            entry = make_entry(request, result.text, (time.perf_counter()-started)*1000)
            responses[request["key"]] = entry
        except (ValueError, TypeError) as exc:
            rejections.append({**{k: request[k] for k in ("key", "source", "source_sha256", "target", "prompt_sha256", "attempt")},
                               "raw": result.text, "error": str(exc), "generation_ms": (time.perf_counter()-started)*1000})
            print(f"Translation {i+1}/{len(config['requests'])}: rejected {type(exc).__name__}", flush=True)
        output = {"responses": list(responses.values()), "rejections": rejections}
        tmp = response_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2))
        tmp.replace(response_path)
        print(f"Translation {i+1}/{len(config['requests'])}: {(time.perf_counter()-started):.1f}s", flush=True)
        mx.clear_cache()


if __name__ == "__main__":
    main()
