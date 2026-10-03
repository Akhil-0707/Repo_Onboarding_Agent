# %% [markdown]
# # RepoGuide model server (Kaggle, 2x T4)
#
# Serves an instruct model with **vLLM's OpenAI-compatible API** (tool calling on), protects it
# with an API key, and exposes it through a **cloudflared quick tunnel**.
#
# Before running: Settings -> Accelerator **GPU T4 x2**, Internet **on**, and add the Kaggle
# Secret `VLLM_API_KEY` (Add-ons -> Secrets). See `kaggle/README.md` for the full walkthrough.
#
# This notebook is generated from `kaggle/serve_model.py` (`python kaggle/build_notebook.py`).

# %%
# --- Configuration -----------------------------------------------------------------------
import os

# Printed by the install cell: tells which revision of this notebook actually ran.
NOTEBOOK_VERSION = "2026-10-03.3"
MODEL = os.environ.get("MODEL", "Qwen/Qwen3-8B")
# vLLM release to install. If it fails on T4 (compute capability 7.5), try "0.18.1", which the
# community has validated on Kaggle's dual T4 setup.
VLLM_VERSION = os.environ.get("VLLM_VERSION", "0.30.0")
TENSOR_PARALLEL = int(os.environ.get("TENSOR_PARALLEL", "2"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "16384"))
GPU_MEMORY_UTILIZATION = float(os.environ.get("GPU_MEMORY_UTILIZATION", "0.92"))
# Hermes-style tool calls are what Qwen2.5/Qwen3 chat templates emit.
TOOL_CALL_PARSER = os.environ.get("TOOL_CALL_PARSER", "hermes")
PORT = int(os.environ.get("PORT", "8000"))
SERVER_LOG = (
    "/kaggle/working/vllm.log" if os.path.isdir("/kaggle/working") else "vllm.log"
)
TUNNEL_LOG = (
    "/kaggle/working/cloudflared.log"
    if os.path.isdir("/kaggle/working")
    else "cloudflared.log"
)

# %%
# --- Install vLLM ------------------------------------------------------------------------
# Installing vLLM replaces Kaggle's PyTorch. Two things can then break:
# - Kaggle's preinstalled torchaudio is built for another CUDA version, and `transformers`
#   imports it ("PyTorch and TorchAudio were compiled with different CUDA versions").
#   vLLM serves text only, so torchaudio is removed.
# - The new PyTorch may need a newer GPU driver than Kaggle has (e.g. a CUDA 13 build). This
#   is checked in a fresh process, and the community-validated fallback version is installed
#   if PyTorch cannot run on the GPUs.
import json
import re
import shutil
import subprocess
import sys

FALLBACK_VLLM_VERSION = "0.18.1"


def pip(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", *args], check=True)


def driver_cuda_version() -> str:
    try:
        output = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return "unknown (no nvidia-smi: is a GPU accelerator selected?)"
    match = re.search(r"CUDA Version:\s*([\d.]+)", output)
    return match.group(1) if match else "unknown"


def torch_runs_on_gpu() -> tuple[bool, str]:
    probe = (
        "import json, torch\n"
        "ok = torch.cuda.is_available() and torch.cuda.device_count() > 0\n"
        "if ok:\n"
        "    (torch.ones(4, device='cuda') * 2).sum().item()  # needs kernels for this GPU\n"
        "print(json.dumps({'ok': bool(ok), 'torch': torch.__version__,\n"
        "                  'cuda': torch.version.cuda, 'gpus': torch.cuda.device_count()}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        return False, lines[-1] if lines else "PyTorch failed to start"
    info = json.loads(result.stdout.strip().splitlines()[-1])
    return (
        info["ok"],
        f"PyTorch {info['torch']} (CUDA {info['cuda']}), {info['gpus']} GPU(s)",
    )


def run_python(code: str) -> subprocess.CompletedProcess[str]:
    """Fresh interpreter: this kernel may still hold the packages it imported earlier."""
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )


def remove_torchaudio() -> None:
    # Kaggle images can hold more than one copy (several site-packages directories).
    for _ in range(5):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "torchaudio"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "not installed" in result.stdout + result.stderr:
            break
    # A copy pip does not manage (no install record) is deleted directly.
    where = run_python(
        "import importlib.util as u\n"
        "s = u.find_spec('torchaudio')\n"
        "print(s.submodule_search_locations[0] if s and s.submodule_search_locations else '')"
    ).stdout.strip()
    if where:
        shutil.rmtree(where, ignore_errors=True)
        print(f"Removed a torchaudio copy pip could not uninstall: {where}")
    left = run_python("import importlib.util as u; print(u.find_spec('torchaudio'))")
    print(
        f"torchaudio after cleanup: {left.stdout.strip() or left.stderr.strip()[-200:]}"
    )


def vllm_imports() -> tuple[bool, str]:
    """The same imports `vllm serve` does first (they pull in transformers)."""
    result = run_python("import vllm.engine.arg_utils")
    lines = result.stderr.strip().splitlines()
    return result.returncode == 0, lines[-1] if lines else ""


def install_vllm(version: str) -> tuple[bool, str]:
    pip("install", "-q", f"vllm=={version}")
    remove_torchaudio()
    return torch_runs_on_gpu()


print(f"Notebook version {NOTEBOOK_VERSION}")
print(f"GPU driver supports CUDA {driver_cuda_version()}")
ok, detail = install_vllm(VLLM_VERSION)
print(f"vLLM {VLLM_VERSION}: {detail}")
if not ok and VLLM_VERSION != FALLBACK_VLLM_VERSION:
    print(
        f"PyTorch cannot use the GPUs with vLLM {VLLM_VERSION}; trying {FALLBACK_VLLM_VERSION}."
    )
    VLLM_VERSION = FALLBACK_VLLM_VERSION
    ok, detail = install_vllm(VLLM_VERSION)
    print(f"vLLM {VLLM_VERSION}: {detail}")
if not ok:
    raise RuntimeError(
        f"PyTorch cannot use the GPUs ({detail}). Check Session options -> Accelerator: GPU T4 x2."
    )
imports_ok, import_error = vllm_imports()
if not imports_ok:
    raise RuntimeError(
        f"vLLM {VLLM_VERSION} is installed but cannot be imported: {import_error}\n"
        "Paste this cell's output into the RepoGuide session to get it fixed."
    )
print(f"Installed vLLM {VLLM_VERSION}; it imports cleanly.")


# %%
# --- Secrets -----------------------------------------------------------------------------
def read_secret(name: str, required: bool = True) -> str | None:
    """Kaggle Secrets first, then environment variables (for running elsewhere)."""
    try:
        from kaggle_secrets import UserSecretsClient

        value = UserSecretsClient().get_secret(name)
        if value:
            return value
    except Exception:
        pass
    value = os.environ.get(name)
    if required and not value:
        raise RuntimeError(
            f"Secret {name} is not set. Add it under Add-ons -> Secrets."
        )
    return value


API_KEY = read_secret("VLLM_API_KEY")
HF_TOKEN = read_secret("HF_TOKEN", required=False)
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN
print("API key loaded (not printed).")

# %%
# --- Start the vLLM OpenAI-compatible server ---------------------------------------------
import shutil

# T4 GPUs have no bfloat16 and no NVLink: use float16, eager mode and the plain all-reduce.
os.environ.setdefault("NCCL_P2P_DISABLE", "1")
os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")

vllm_bin = shutil.which("vllm") or "vllm"
server_cmd = [
    vllm_bin,
    "serve",
    MODEL,
    "--served-model-name",
    MODEL,
    "--host",
    "0.0.0.0",
    "--port",
    str(PORT),
    "--api-key",
    API_KEY,
    "--dtype",
    "half",
    "--tensor-parallel-size",
    str(TENSOR_PARALLEL),
    "--max-model-len",
    str(MAX_MODEL_LEN),
    "--gpu-memory-utilization",
    str(GPU_MEMORY_UTILIZATION),
    "--enforce-eager",
    "--disable-custom-all-reduce",
    "--enable-auto-tool-choice",
    "--tool-call-parser",
    TOOL_CALL_PARSER,
]
server_log = open(SERVER_LOG, "w")  # noqa: SIM115 - kept open for the server's lifetime
server_proc = subprocess.Popen(server_cmd, stdout=server_log, stderr=subprocess.STDOUT)
print(f"vLLM starting (pid {server_proc.pid}); logs in {SERVER_LOG}")

# %%
# --- Wait until the model is loaded -------------------------------------------------------
import time
import urllib.error
import urllib.request

LOCAL_BASE = f"http://127.0.0.1:{PORT}/v1"


def server_ready() -> bool:
    request = urllib.request.Request(
        f"{LOCAL_BASE}/models", headers={"Authorization": f"Bearer {API_KEY}"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=5
        ) as response:  # noqa: S310 - localhost
            return response.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False


def tail(path: str, lines: int = 25) -> str:
    try:
        with open(path, errors="replace") as handle:
            return "".join(handle.readlines()[-lines:])
    except OSError:
        return ""


deadline = time.time() + 30 * 60  # first start downloads ~16 GB of weights
while not server_ready():
    if server_proc.poll() is not None:
        raise RuntimeError("vLLM exited during startup:\n" + tail(SERVER_LOG, 60))
    if time.time() > deadline:
        raise TimeoutError(
            "vLLM did not become ready in 30 minutes:\n" + tail(SERVER_LOG, 60)
        )
    time.sleep(10)
    print(".", end="", flush=True)
print("\nvLLM is ready.")

# %%
# --- Start a cloudflared quick tunnel ----------------------------------------------------
import re
import stat

CLOUDFLARED = (
    "/kaggle/working/cloudflared"
    if os.path.isdir("/kaggle/working")
    else "./cloudflared"
)
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
if not os.path.exists(CLOUDFLARED):
    urllib.request.urlretrieve(
        CLOUDFLARED_URL, CLOUDFLARED
    )  # noqa: S310 - official release
    os.chmod(CLOUDFLARED, os.stat(CLOUDFLARED).st_mode | stat.S_IEXEC)

TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def start_tunnel() -> tuple[subprocess.Popen, str]:
    log = open(TUNNEL_LOG, "w")  # noqa: SIM115
    proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(90):
        match = TUNNEL_PATTERN.search(tail(TUNNEL_LOG, 200))
        if match:
            return proc, match.group(0)
        if proc.poll() is not None:
            break
        time.sleep(1)
    raise RuntimeError(
        "cloudflared did not report a tunnel URL:\n" + tail(TUNNEL_LOG, 40)
    )


tunnel_proc, public_url = start_tunnel()
PUBLIC_BASE = f"{public_url}/v1"
print("=" * 72)
print(f"Public URL:  {PUBLIC_BASE}")
print("Put this in your RepoGuide .env:")
print(f"  LLM_BASE_URL={PUBLIC_BASE}")
print(f"  LLM_MODEL={MODEL}")
print("Or update a running stack without restarting:")
print(f"  docker compose exec backend python manage.py set_llm_url {public_url}")
print("=" * 72)

# %%
# --- Smoke test: a completion and a tool call through the public URL ---------------------
from openai import OpenAI

client = OpenAI(base_url=PUBLIC_BASE, api_key=API_KEY, timeout=120)
no_thinking = {"chat_template_kwargs": {"enable_thinking": False}}

reply = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "user", "content": "Reply with exactly: RepoGuide model online"}
    ],
    max_tokens=20,
    temperature=0,
    extra_body=no_thinking,
)
print("Completion:", reply.choices[0].message.content)

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the repository",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]
reply = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Open the README.md file."}],
    tools=tools,
    tool_choice="auto",
    temperature=0,
    extra_body=no_thinking,
)
calls = reply.choices[0].message.tool_calls or []
print("Tool calls:", [(c.function.name, c.function.arguments) for c in calls])
if not calls:
    print(
        "WARNING: no structured tool call returned; check TOOL_CALL_PARSER for this model."
    )

# Requests without the key must be rejected.
try:
    OpenAI(base_url=PUBLIC_BASE, api_key="wrong-key").models.list()
    print("WARNING: server accepted a wrong API key!")
except Exception:
    print("Auth check: requests without the right key are rejected.")

# %%
# --- Keep alive: report status and restart the tunnel if it dies -------------------------
# Kaggle stops idle interactive sessions; keep this cell running. Stop it to shut down.
try:
    while True:
        if server_proc.poll() is not None:
            print("vLLM exited:\n" + tail(SERVER_LOG, 40))
            break
        if tunnel_proc.poll() is not None:
            print("Tunnel died; starting a new one...")
            tunnel_proc, public_url = start_tunnel()
            print(f"NEW URL: {public_url}/v1  ->  set_llm_url {public_url}")
        print(
            time.strftime("%H:%M:%S"), "alive:", server_ready(), public_url, flush=True
        )
        time.sleep(60)
except KeyboardInterrupt:
    print("Stopping.")
finally:
    tunnel_proc.terminate()
    server_proc.terminate()
