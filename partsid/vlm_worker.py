"""Isolated MLX process: pinned model, image evidence, checkpointed raw outputs."""
import importlib.metadata
import json
import sys
import time
from pathlib import Path


def cache_matches(response, request, config):
    return (all(response.get(key) == request.get(key) for key in ("key", "prompt_sha256", "images_sha256"))
            and isinstance(request.get("images_sha256"), list)
            and all(response.get(key) == config.get(key) for key in ("max_pixels", "max_tokens")))


def main():
    import mlx.core as mx
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    request_path, response_path = map(Path, sys.argv[1:3])
    config = json.loads(request_path.read_text())
    mx.random.seed(0)
    start = time.perf_counter()
    model, processor = load(config["model"], revision=config["revision"], trust_remote_code=False)
    runtime = {p: importlib.metadata.version(p) for p in ("mlx", "mlx-vlm", "transformers")}
    output = {"model": config["model"], "revision": config["revision"], "model_load_s": time.perf_counter() - start,
              "runtime": runtime, "responses": []}
    if response_path.exists():
        old = json.loads(response_path.read_text())
        if old.get("model") == config["model"] and old.get("revision") == config["revision"]:
            output["responses"] = old.get("responses", [])
    for i, request in enumerate(config["requests"]):
        cached = next((r for r in output["responses"] if cache_matches(r, request, config)), None)
        if cached:
            print(f"VLM {i + 1}/{len(config['requests'])}: cached", flush=True)
            continue
        prompt = apply_chat_template(processor, model.config, request["prompt"], num_images=len(request["images"]))
        start = time.perf_counter()
        result = generate(model, processor, prompt, image=request["images"], max_tokens=config["max_tokens"],
                          max_pixels=config["max_pixels"], min_pixels=65536, temperature=0.0, verbose=False)
        response = {k: request[k] for k in ("key", "prompt_sha256", "input_sha256", "images_sha256")}
        response.update(raw=result.text, ms=(time.perf_counter() - start) * 1000,
                        max_pixels=config["max_pixels"], max_tokens=config["max_tokens"],
                        generation_tokens=result.generation_tokens, peak_memory=result.peak_memory)
        output["responses"] = [r for r in output["responses"] if r["key"] != request["key"]] + [response]
        tmp = response_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2))
        tmp.replace(response_path)
        print(f"VLM {i + 1}/{len(config['requests'])}: {response['ms'] / 1000:.1f}s", flush=True)
        mx.clear_cache()


if __name__ == "__main__":
    main()
