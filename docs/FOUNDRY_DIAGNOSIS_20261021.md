# Foundry failure: evidence, fixes and one remaining runtime check

Date: 21 October 2026. Baseline: shared main `d3952a1`. Diagnosis branch:
`fix/foundry-runtime-diagnostics`. No scoring changes, secrets, key rotation,
Azure settings changes or production deployment are included in this branch.

## Observed, not assumed

| Layer | Check | Result / limit |
| --- | --- | --- |
| Deployment | GitHub run 39456955287, commit d3952a1 | Build and deployment succeeded. This does not prove a provider request succeeded. |
| Dependencies | Build log | openai 3.35.1, httpx2 2.15.1, pydantic 2.14.1. App Service can rebuild separately, so these are build versions, not proof of runtime versions. The patch exposes actual installed versions in health/doctor output. |
| Web app | Production /healthz | HTTP 200, integrated-room-v1, llm_configured=true, connectivity_verified=false. |
| Small explanation | Liverpool minute 5, wait plan, fan/English | HTTP 200; source=template, note=LLM_UNAVAILABLE, cached=false, about 750 ms. |
| Full explanation | Liverpool minute 65, attack/win, second choice swap:3535:3380, analyst/English | HTTP 200; source=template, note=LLM_UNAVAILABLE, cached=false, about 562 ms. |
| Documented endpoint from this machine | DNS + verified HTTPS to live-sub-intel-resource.openai.azure.com/openai/v1/models, without a key | DNS resolves; Azure returns HTTP 401. Proves reachability from this machine only, not correct resource/key/deployment or App Service networking. |
| Exact build SDK | Installed openai 3.35.1 + httpx2 2.15.1 in an isolated folder; sent the same v1 chat request with an explicitly invalid dummy key | AuthenticationError, HTTP 401, about 1.06 seconds. SDK construction, serialization, URL and this machine's TLS transport work. This is NOT a successful authenticated model response. |
| Real SDK wire tests | Local HTTP provider, actual SDK 2.32.0 and 3.35.1 | Correct /openai/v1/chat/completions request, model, JSON mode, token bound. Valid provider response is accepted; 400/401/403/404/429/503 map to the expected diagnosis. No paid calls. |
| Azure runtime logs | Opened Azure portal | No authenticated Azure session here. App Service settings, provider status and runtime log cause could not be read. |

The failure occurs in both a tiny no-change context and a full tactical context.
This makes a problem specific to the second-choice UI or large plan payload
unlikely. The old response hides the provider's error type/status, so it is not
possible to distinguish authentication, resource policy, route/deployment,
request incompatibility or transport conclusively from `LLM_UNAVAILABLE` alone.
Do not claim that keys, quotas or TLS are the established root cause.

HTTP 200 from the app is deliberate fallback behavior, not evidence that Foundry
answered. Likewise, llm_configured previously meant only that three raw values
were nonempty. A successful provider response and source=llm remain the proof.

## Concrete fixes in this branch

1. **Correct endpoint parsing.** The previous string search for `/openai` also
   matched a hostname beginning with `openai-...` and could construct a request
   to the wrong host. Normalize only the parsed URL path. The documented project
   resource does not start this way; this is a proven bug, not a claim that it
   caused the currently deployed failure.
2. **Validate settings before sending them.** Check HTTPS URL shape, supported
   endpoint paths, deployment-name format, missing/whitespace-only values and
   quoted, non-ASCII or multiline keys. Continue trimming outer whitespace.
   Invalid values are not echoed in errors, health or logs. Key values are
   excluded from configuration reprs.
3. **Separate failing stages.** Configuration, SDK/client setup, provider request
   and model-output validation now have separate safe diagnostics. A bad key
   format is no longer called bad model output. DNS, TLS, timeout, HTTP 401,
   403, 404, 400, 429 and provider failures have actionable categories.
4. **Return a reference and safe error code.** Explanation replies and the
   interface include a correlation reference. Health includes validated config,
   actual installed SDK versions and the last meaningful explanation outcome.
   Cooldown replies do not overwrite the original failure. No raw provider body,
   key, request headers or arbitrary nested exception message is exposed.
5. **Stop logging raw nested causes.** Invalid HTTP-header errors can embed the
   offending credential value. Logs now contain classification, stage, status,
   exception/cause TYPES and reference, never that message.
6. **Keep provider bounds at construction.** The shared client factory now sets
   the same 12-second timeout and zero SDK retries as the integrated caller.
7. **Provide a runtime doctor.** `scripts/diagnose_foundry.py` performs a zero-call
   preflight by default, one tiny provider call with --live, and at most two
   provider calls with --full. The second call uses the actual second-choice
   plan and full fact-selection contract, only if the first succeeded.

The cache, tactical scoring, audiences and verified-fact renderer remain intact.
The health connectivity flag now reflects the last meaningful explanation's
source, with `connectivity_basis=last_explanation_result`. It never silently
makes a model call and is not a continuous guarantee of provider availability.

## One remaining action in the actual Azure environment

After deploying this small branch, click Explain once and read `/healthz` or the
explanation reply: `diagnostic.code`, `stage`, `status`, `reference`. No access
to raw logs is needed to distinguish the major categories anymore.

Alternatively, in App Service SSH/console, use the **same Python/virtual
environment and App settings as the running app**, from the project directory:

```bash
python scripts/diagnose_foundry.py --full
```

Do not paste keys into the command or chat. The JSON report is designed for
sharing: configuration summary, runtime versions, bounded checks and safe
diagnostics. If `SDK_NOT_INSTALLED` appears only in the shell, first verify the
shell is using the application's Python environment; do not diagnose the app
from an unrelated shell environment.

| Diagnostic | Next targeted check |
| --- | --- |
| CONFIG_* | Correct the named App setting's format; no provider call was made. |
| AUTHENTICATION_FAILED / 401 | Verify the key belongs to this resource endpoint and the current regenerated key is in App settings. A wrong endpoint/key pair can produce the same status. |
| RESOURCE_ACCESS_DENIED / 403 | Resource network/firewall/access policy from the App Service environment. |
| DEPLOYMENT_OR_ROUTE_NOT_FOUND / 404 | Actual deployment NAME and route on the same resource. |
| PROVIDER_BAD_REQUEST / 400 | Installed SDK/model request-parameter compatibility. |
| PROVIDER_RATE_LIMIT_OR_QUOTA / 429 | Deployment quota, billing and throttling. |
| DNS_LOOKUP_FAILED | Actual configured hostname and private/public DNS from App Service. |
| TLS_VERIFICATION_FAILED | Hostname, trusted CA chain and TLS proxy settings; retain certificate verification. |
| NETWORK_TIMEOUT / CONNECTION_FAILED | Outbound network and actual provider reachability. |
| MODEL_RESPONSE_REJECTED | The provider answered; inspect the strict fact-selection contract rather than changing credentials. |

Fallback results cache for 30 seconds; global cooldown is 15 seconds. Allow
those to expire before interpreting a repeat result after a change. Applying
App settings normally restarts the app and clears its process-local cache.

## Verification

Regression coverage includes endpoint-host parsing, secret-free config/error
output and logs, nested DNS/TLS/timeout causes, real installed SDK wire requests
and HTTP failure statuses, and bounded doctor preflight/success/auth/output
paths. Existing complete-XI, locale, cache, audience and HTTP tests are retained.
No claim of production model success is made by these local/simulated checks.

References checked while investigating:

- [Official OpenAI SDK HTTPX2 migration and TLS trust-store changes](https://github.com/openai/openai-python/blob/main/httpx2.md).
- [Microsoft v1 structured-output examples and deployment-name usage](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).
- [Successful deployment run](https://github.com/TomThomasPrintac/live-sub-intel/actions/runs/39456955287).

Final local verification: **187 Python tests passed with openai 3.35.1 /
httpx2 2.15.1**, plus **8 Node tests**. The final safe-provider-field change
also passed the 33 runtime-specific tests. Earlier wire/config tests passed
with the installed 2.32.0 SDK as well. These are software/transport checks,
not a successful authenticated request in the production App Service.
