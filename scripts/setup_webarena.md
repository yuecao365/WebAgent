# WebArena Verified shopping-admin on Windows 11

How the local evaluation site is set up on this machine: Windows 11, Docker Desktop
with the WSL2 backend, Docker data on D:. Only the shopping-admin site is used.

Sources: the WebArena Verified repository (commit 6473f72, package 1.2.3) and its
`docs/environments/` pages.

## What runs where

| Piece | Where | Notes |
|---|---|---|
| Site (Magento 2 admin) | Docker container `webarena-verified-shopping_admin` | http://localhost:7780/admin |
| Environment control (`env-ctrl`) | same container | http://localhost:7781 (status, init, start, stop) |
| Evaluator and dataset | Python package `webarena-verified` in `.venv` | runs in-process, no network |
| Browser | Edge or Chrome on Windows, started by the harness | dedicated profile under `BROWSER_AGENT_DATA_DIR` |

Image: `am1n3e/webarena-verified-shopping_admin:0.1.0` from Docker Hub
(digest `sha256:d0531dd27ed9…`, the same image as `latest` on 2026-11-16). Download
1.25 GB; `docker images` reports 4.49 GB on disk. A running container uses about
1.1 GB of memory.

## One-time setup

1. **Docker Desktop with WSL2.** Install Docker Desktop and keep "Use the WSL 2 based
   engine" on.

2. **Move Docker's data to D:.** Docker Desktop → Settings → Resources → Advanced →
   *Disk image location* → `D:\Docker` → Apply & restart. Docker moves the existing
   data. Check:

   ```powershell
   Get-Content "$env:APPDATA\Docker\settings-store.json"   # "CustomWslDistroDir": "D:\\Docker\\DockerDesktopWSL"
   Get-ChildItem D:\Docker -Recurse -Filter *.vhdx
   ```

3. **Pull the image** (1.25 GB; ask before pulling, see AGENTS.md):

   ```powershell
   docker pull am1n3e/webarena-verified-shopping_admin:0.1.0
   ```

4. **Python environment.** uv keeps its cache and its Python on D::

   ```powershell
   $env:UV_CACHE_DIR = "D:\uv-cache"; $env:UV_PYTHON_INSTALL_DIR = "D:\uv-python"
   uv sync
   ```

5. **`.env`.** Copy `.env.example` to `.env`. The site settings have working
   defaults; the model settings are needed only for paid runs.

## Start, stop, reset

```powershell
# start (about 50–80 seconds until the admin answers)
docker run -d --name webarena-verified-shopping_admin `
  -p 127.0.0.1:7780:80 -p 127.0.0.1:7781:8877 `
  -e WA_ENV_CTRL_EXTERNAL_SITE_URL=http://localhost:7780 `
  am1n3e/webarena-verified-shopping_admin:0.1.0

# status
curl.exe http://localhost:7781/status

# stop and delete
docker rm -f webarena-verified-shopping_admin
```

- Ports are published on 127.0.0.1 only, so the site is not reachable from the
  network.
- `WA_ENV_CTRL_EXTERNAL_SITE_URL` sets Magento's base URL when the container starts.
  It must be the URL the browser uses.
- **Reset means a new container.** The `env-ctrl` service has no reset endpoint
  (`POST /reset` returns 404, although one page of the documentation mentions it). The
  official `SiteHandler.reset()` deletes the container and starts a new one from the
  image; `ShoppingAdmin.reset()` in `src/browser_agent/eval/webarena.py` does the same
  and then waits until the services are healthy and the admin signs in twice in a
  row. A reset took 78 seconds here.

## Signing in

The image accepts a header instead of the login form:

```
X-M2-Admin-Auto-Login: admin:admin1234
```

These are the benchmark's published test credentials. The harness sends the header
with every request of its tab (`Network.setExtraHTTPHeaders`).

## Check the environment

```powershell
$env:BH_TELEMETRY = "0"
uv run python scripts/check_env.py
```

It needs the container running and calls no model. It checks that:

1. the site loads in the harness browser and the dashboard can be read;
2. the official evaluator scores a task from the harness's own network trace (task
   157, one navigation: the correct run scores 1.0 and a wrong answer scores 0.0);
3. a reset restores state (a value changed in the database is back afterwards).

## Problems met and how they were solved

- **Docker data was on C:.** Moved with the Docker Desktop setting above.
- **`localhost` is slow from command-line clients.** `curl http://localhost:7780` takes
  about 0.2 s longer per connection than `http://127.0.0.1:7780`, because the IPv6
  address is tried first and the port is published on IPv4 only. The browser reuses
  connections and is not affected. The site URL stays `localhost` because Magento
  redirects to its base URL.
- **Pages took 40 seconds to render and grid rows came back empty.** Both came from
  browser-harness putting a named daemon into a background tab, which Chrome throttles
  and does not lay out. See DECISIONS.md, "前台标签页". After the fix a grid page is
  ready in 2–5 seconds.
- **No Chrome on this machine.** Edge is used; set `BROWSER_PATH` to use another
  Chromium browser.
