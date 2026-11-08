# Local inference performance and reliability

The public API, required result fields, canonical source IDs, Decimal scorer and
strict grounding/semantic checks are unchanged. The model wire now emits an explicit
`applicability` status inside each finding, before its answer. A single short reason
explains applicability and judgment. Parsing expands that decision into the existing
root applicability list; it never derives applicability from the score or invents an
answer. Legacy saved responses remain readable.

Model-only limits: 240-character reasons, 160-character summary and at most two
additional sources. For small inputs, quote choices are literal source clauses or
adjacent clauses/windows of at most 160 characters. Inputs yielding more than 64
choices retain free verbatim quoting with the previous 300-character limit, without
dropping messages. This avoids the observed failure where a length-only limit made
the model alter spaces while trying to copy a longer quote. ID/role/quote/relevance
checks still run after generation; selecting a real span does not establish a correct
judgment. Optional empty fields and
duplicate primary evidence should be omitted. Public validation still supports the
existing larger records. Full conversation messages are supplied without truncation.
Critic independently reviews the selected risk/dispute criteria and the application
preserves other findings. It still checks N/A and numeric judgments conservatively;
this change does not eliminate the second quality-control pass.

The compact `review` string is empty unless there is material uncertainty; a nonempty
value expands into the existing review flag/reason/notes. The live draft had populated
the old optional reviewReason with routine successful observations even while its
review flag was false. Validation conservatively promoted those notes to review
requests, expanding Critic to all eight criteria and duplicating explanations.
The final wire removes that duplicate output channel. The exact-span and review-field
fixes were automated/offline-tested after the CPU live attempt; no further real
generation was started to verify them.

Targeted repairs now merge parsed corrections before revalidating the combined result.
Previously, fixing A while B remained invalid could lose the correction to A and
send later repairs back to an already solved problem. Replacements must cover exactly
the selected IDs and cannot overwrite unselected results. Invalid full JSON is no
longer fed back as a verbose assistant answer. Failed jobs retain safe phase, repair,
validation category and invalid criterion IDs in worker metrics, without transcript
or raw-error text.

Each phase permits three generations: Draft plus two repairs, then Critic plus two
repairs. Thus the normal two_pass maximum is **six** generations (with one HTTP
attempt each), not four. The benchmark defaults now allow two evaluations/twelve
generations within one shared 720-second budget. A timeout can still stop the work.
Use `--repeats 1 --max-evaluations 2 --max-model-calls 12 --deadline-seconds 720`;
do not reset that budget in another process. Multi-agent strategy has a different call
count and is outside this performance verification.

## Hardware check before inference

On 2026-11-08 Windows reported NVIDIA RTX 4060 **ConfigManagerErrorCode 43**;
`nvidia-smi` failed and a new Ollama process discovered only CPU. That is a GPU/driver
availability blocker, not an output-schema or FastAPI problem. No driver changes or
OS restart are performed by these instructions. Restore normal GPU availability
before attempting to measure GPU acceleration.

```powershell
Get-CimInstance Win32_VideoController | Select-Object Name,Status,ConfigManagerErrorCode
nvidia-smi
```

The earlier 32K/f16 run offloaded 31/37 layers and used about 4.5 GiB of KV cache.
Flash Attention was already active. Output decoding, extra repairs and partial CPU
residency explain the observed latency costs; prompt prefill and queueing were small.
The exact speed gain from full GPU offload is unmeasured while Code 43 persists.

Ollama documents that Flash Attention permits quantized KV cache; q8_0 uses roughly
half the f16 cache memory, with possible model/task-dependent precision effects.
These are server settings requiring a server restart. Verify actual cache type,
offloaded layers and residency in logs, not just environment variables.
[Official Ollama configuration and KV-cache documentation](https://docs.ollama.com/faq#how-can-i-set-the-quantization-type-for-the-kv-cache).

## Optimized local startup (after GPU recovery)

In a fresh PowerShell window, start a local server on an unused loopback port. This
leaves the existing daemon on 11434 and persistent user environment unchanged:

```powershell
$gpu = Get-CimInstance Win32_VideoController | Where-Object Name -Match 'NVIDIA'
if (-not $gpu -or $gpu.ConfigManagerErrorCode -ne 0) { throw 'Restore the NVIDIA device before GPU testing.' }
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_CONTEXT_LENGTH = '24576'
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```

In another PowerShell window:

```powershell
Set-Location C:\Users\Insar\hackathon-data-challenge
$env:PYTHONPATH = "$PWD\src"
$env:LLM_PROVIDER = 'ollama'
$env:LLM_BASE_URL = 'http://127.0.0.1:11435'
$env:LLM_MODEL = 'qwen3:4b-instruct'
$env:CQA_STRATEGY = 'two_pass'
$env:CQA_ENABLE_CRITIC = 'true'
$env:CQA_WORKERS = '1'
$env:LLM_CONCURRENCY = '1'
$env:LLM_ATTEMPTS = '1'
$env:LLM_CONTEXT_SIZE = '24576'
$env:LLM_OUTPUT_LIMIT = '2500'
$env:LLM_TIMEOUT = '300'
$env:CQA_JOB_TIMEOUT = '720'
$env:DATABASE_URL = 'sqlite:///.runtime/optimized-local-demo.db'
& C:\Users\Insar\cqa-ai-venv\Scripts\python.exe -m uvicorn cqa.api:app --host 127.0.0.1 --port 8784
```

Open http://127.0.0.1:8784. Keep both terminals running. Inspect `ollama ps` with
`OLLAMA_HOST=127.0.0.1:11435` and the corresponding server log. `size_vram=0` means
this is a CPU run even when the laptop physically contains an NVIDIA GPU.

The measured conservative input bounds for the short synthetic case and selected
12-message private case fit 24K with the 2500-token output reserve. This is not a
universal limit for large dynamic checklists. The provider checks full UTF-8 prompt
bytes plus output reserve and 1024 margin before generating, then checks reported
input tokens too. If a real input fails the guard, inspect its size and select a
sufficient larger context; do not remove relevant messages or disable validation.
An output ending at num_predict is an error, never a partial saved assessment.

Revert: stop these two terminals with Ctrl+C and close them. To restore f16 in a
future server process, omit OLLAMA_KV_CACHE_TYPE or set it to f16. Restore the old
context/output settings explicitly if needed. No permanent environment values,
models, drivers, data, existing daemon or infrastructure have been changed.

## Interpreting measurements

Compare completed cases with identical normalized input and checklist fingerprints.
Keep input/output token counts, per-phase latency, repair targets, residency, cache
type, output limit, context, model digest and cold/warm state. A failure stopped by
a harness budget is not proof of production evaluator failure. CPU-only measurements
cannot establish a speedup over a previous GPU run. Quantized-cache quality and
real repeated-run semantic consistency require separate evidence.

Private inputs, labels, raw model responses and DBs stay outside Git worktrees. The
source-controlled regression tests use synthetic fixtures only. The manual labeling
protocol is [cqa-labeling-protocol.md](cqa-labeling-protocol.md).
