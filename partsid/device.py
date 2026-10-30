import torch


def pick_device(requested: str | None = None) -> str:
    """cuda (e.g. RTX 5080) > Apple mps > cpu, unless a device is given explicitly."""
    if requested:
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise SystemExit(f"--device {requested}: torch {torch.__version__} sees no CUDA GPU "
                             "(CPU-only wheel, or an NVIDIA driver too old for its CUDA version)")
        if requested == "mps" and not torch.backends.mps.is_available():
            raise SystemExit("--device mps: this torch build or machine has no MPS backend")
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def synchronize(device: str) -> None:
    """Wait for queued GPU work so wall-clock timings measure the real cost."""
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    elif device == "mps":
        torch.mps.synchronize()


def describe(device: str) -> str:
    if device.startswith("cuda"):
        return f"cuda ({torch.cuda.get_device_name(0)})"
    if device == "mps":
        return "mps (Apple GPU)"
    return "cpu"
