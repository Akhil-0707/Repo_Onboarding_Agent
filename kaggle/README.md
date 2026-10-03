# Kaggle model server

RepoGuide uses a self-hosted open model. This folder runs it for free on a Kaggle GPU notebook:
**vLLM** serves `Qwen/Qwen3-8B` in float16 across Kaggle's **2× Tesla T4** (tensor parallel = 2)
with an OpenAI-compatible API, tool calling turned on, and an API key. A **cloudflared quick
tunnel** gives it a public HTTPS URL that the RepoGuide backend calls.

| File | Purpose |
|---|---|
| `serve_model.ipynb` | The notebook to upload to Kaggle |
| `serve_model.py` | The same code as a script (source of truth; percent-format cells) |
| `build_notebook.py` | Regenerates the notebook from the script |

## Why these settings

- **float16**: T4s (compute capability 7.5) have no bfloat16 support.
- **Qwen3-8B, TP=2**: about 16.4 GB of fp16 weights, so about 8.2 GB per 15 GB T4, leaving room
  for the KV cache at a 16k context.
- **`--tool-call-parser hermes`**: Qwen chat templates emit Hermes-style `<tool_call>` blocks.
- **`--enforce-eager --disable-custom-all-reduce`**: T4s have no NVLink, and CUDA graphs waste
  scarce memory. These are the settings validated by the community on Kaggle T4s.
- **Thinking disabled per request** (`chat_template_kwargs.enable_thinking=false`): faster
  answers and clean JSON for structured sections.

## Step by step

1. **Create the notebook.** On kaggle.com choose *Create → New Notebook*, then
   *File → Import Notebook* and upload `kaggle/serve_model.ipynb`.
2. **Pick the accelerator.** In the right-hand panel, open *Session options → Accelerator* and
   choose **GPU T4 x2**. The P100 option has a single GPU and does not support this config.
3. **Turn on internet.** In the same panel, switch **Internet** on. Kaggle requires a
   phone-verified account for this, which you do once under *Settings → Phone verification*.
4. **Add secrets.** Open *Add-ons → Secrets* and add the following, then tick *Attach* for this
   notebook:
   - `VLLM_API_KEY`: any long random string, e.g. the output of
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Every request must send it.
   - `HF_TOKEN` (optional): a Hugging Face read token, which gives faster and more reliable
     model downloads.
5. **Run all cells.** The first start installs vLLM and downloads about 16 GB of weights
   (10–20 minutes). Later sessions are faster when the weights are cached.
6. **Copy the URL.** When the tunnel cell finishes, it prints something like:
   ```
   Public URL:  https://example-words-here.trycloudflare.com/v1
     LLM_BASE_URL=https://example-words-here.trycloudflare.com/v1
   ```
   RepoGuide needs the **API key once**: put `LLM_API_KEY=<the same value as the
   VLLM_API_KEY secret>` in RepoGuide's `.env` (create the file if you have none; one line is
   enough) and run `docker compose up -d` so the containers pick it up. The key never changes
   between sessions.
   Then point the running stack at the URL (repeat this whenever the URL changes):
   ```bash
   docker compose exec backend python manage.py set_llm_url https://example-words-here.trycloudflare.com
   ```
   The new URL is used within about 10 seconds, with no restart needed. Without `--model`, the
   command uses `LLM_MODEL` (default `Qwen/Qwen3-8B`), or the server's only model if it serves
   exactly one, and clears any model chosen for a previous server (e.g. a local Ollama). If it
   says the server *rejected the API key*, check `LLM_API_KEY` in `.env`.
7. **Leave the last cell running.** It reports liveness every minute and restarts the tunnel if
   it drops. If the tunnel restarts, it prints a **new URL**, so run `set_llm_url` again.

## Session limits and what RepoGuide does about them

Kaggle GPU sessions are time-limited (roughly 12 hours per session, plus a weekly GPU
quota), and idle sessions are stopped. Quick-tunnel URLs change on every start. RepoGuide is
built for this:

- Every LLM call has timeouts and retries with exponential backoff.
- When the model disappears mid-analysis, the job switches to **waiting for model**. It resumes
  automatically from the last completed section once the health check passes again.
- Chat is disabled with a clear banner while the model is offline.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `vLLM exited during startup` mentioning CUDA / kernels / compute capability | Set `VLLM_VERSION = "0.18.1"` in the config cell (community-validated on 2× T4) and re-run. |
| NCCL or tensor-parallel errors | Set `TENSOR_PARALLEL = 1`, and use a 4-bit build such as `MODEL = "Qwen/Qwen3-8B-AWQ"` so it fits one T4. |
| Out of memory | Lower `MAX_MODEL_LEN` (e.g. 8192) or `GPU_MEMORY_UTILIZATION` (e.g. 0.88). |
| `no structured tool call returned` | The model/parser pair is wrong. Qwen models use `hermes`. RepoGuide also parses text tool calls as a fallback. |
| RepoGuide banner says *model offline* | Check the last cell is still running, then run `set_llm_url` with the latest URL. |

## Using a different provider

The backend talks to any OpenAI-compatible server. For local Ollama, for example:

```bash
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3:8b
LLM_DISABLE_THINKING=false
LLM_GUIDED_JSON=false
```
