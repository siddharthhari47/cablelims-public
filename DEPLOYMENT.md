# CableLIMS — Installing on CTL's Server

This guide assumes a Windows machine on CTL's own local network, set up by someone comfortable
with basic Windows administration (installing software, using Task Scheduler, allowing an app
through the firewall) but not necessarily a software developer. No AI assistance is needed to
follow it.

**What you end up with:** one program running quietly in the background on the server, reached
over HTTPS. Everyone on the lab's network — the Scientist's desktop, Scientific Assistants'
phones — opens a secure web address pointed at that server. Nothing is installed on the phones;
they just use their browser.

---

## 1. What the server needs installed

- **Python 3.12 or later.** Download the official installer from https://www.python.org/downloads/
  — during install, tick **"Add python.exe to PATH"**.
- **Node.js is NOT required on the server.** It's only needed once, to produce the website files
  — you can do that step on any other computer (e.g. the machine this was built on) and copy the
  result over. See step 3.
- **Caddy** (for HTTPS — see step 7). A single `.exe`, no installer, no other dependencies —
  download it in step 7, no need to get it now.

That's it — no database server, no IIS, no Docker, nothing else to install.

## 2. Copy the project to the server

Copy the whole `cablelims` folder to the server, e.g. to `C:\CableLIMS\cablelims`.
**Do not copy** the `backend\venv` folder or the `frontend\node_modules` folder if they exist —
they're large, machine-specific, and get recreated fresh in the steps below. If they're already
in the folder you're copying, it's fine, they'll simply be overwritten.

## 3. Build the website files (one time, do this on the dev machine, not the server)

On the machine where this was developed (which already has Node.js), open a terminal in
`cablelims\frontend` and run:
```
npm run build
```
This creates a `frontend\dist` folder — the entire compiled website as plain files. Copy that
`dist` folder onto the server, into `cablelims\frontend\dist`, alongside everything else you
copied in step 2. The backend automatically serves it from there — that's the whole trick to
needing only one process, and no Node.js, on the server itself.

*(If the server does happen to have Node.js and you'd rather build directly on it, `cd
cablelims\frontend`, `npm install`, then `npm run build` — same result, no need to copy `dist`
separately.)*

## 4. Set up the backend

Open a Command Prompt **on the server**, in the `cablelims\backend` folder:
```
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

**Create the initial data** (standard/test configuration only — no demo accounts):
```
venv\Scripts\python -m app.seed --config-only
```
**Create your first real login** (there is no default/demo password on this install path):
```
venv\Scripts\python -m app.create_user
```
This asks for a username, name, role, and a password you choose, right there in the terminal —
nothing is written down anywhere. Run it again any time to add more accounts (Scientists,
Scientific Assistants, more Administrators) or to reset a forgotten password. Once you have an
Administrator account, you can also create/manage accounts from the app itself under
**Administration → Users**.

*(There is a `venv\Scripts\python -m app.seed` — without `--config-only` — that additionally
creates demo accounts (`scientist1`/`assistant1`/`admin1`, password `demo1234`) and two example
samples. That command is for internal development/demos only and refuses to do anything beyond
the plain configuration seed unless `CABLELIMS_ALLOW_DEMO_USERS=1` is also set in the
environment. **Never set that variable, and never run the bare command, on CTL's server** — see
section 9.)*

**Optional: adjust configuration.** `backend\.env.example` lists every operational setting the app
reads (session length, upload size limit, log rotation, backup retention, and more) with its
default and a description. Most installs never need to touch this — the defaults are sane for a
single lab. To change one, copy `.env.example` to `.env` in the same `backend` folder, uncomment
the line(s) you want to change, and restart the app (step 6). Never commit or hand out a real
`.env` file if it ever contains anything sensitive.

**Rotating the signing key.** The app generates a random signing key the first time it ever runs
and reuses it from then on (`backend\data\.secret_key`) — this is what every login session's token
is cryptographically signed with. Rotate it (generate a new one) if you have any reason to believe
it may have leaked, or as routine periodic hygiene:
1. Generate a new random value, e.g. in PowerShell: `-join ((48..57)+(65..90)+(97..122)|Get-Random -Count 48|%{[char]$_})`.
2. Set it as `CABLELIMS_SECRET_KEY` in `backend\.env` (add the line if it isn't there yet — see
   `.env.example` for the exact name).
3. Restart the app (step 6).

**This logs everyone out — on purpose.** Every existing session's token was signed with the old
key, so rotating invalidates all of them at once; that's the entire point of a rotation, not a
side effect to work around. Anyone using the app just needs to log in again. If this install was
ever built from a package predating this note, rotate now (C2) — its key may have been read.

## 5. Test it once, manually

Still in `cablelims\backend`:
```
venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
```
On the server itself, open a browser to `http://localhost:8000` — you should see the CableLIMS
login page. If that works, press `Ctrl+C` to stop it, and move on to making it run permanently.

*(Binding to `127.0.0.1` rather than `0.0.0.0` means the app itself is only reachable from this
machine — that's intentional, not a mistake. Step 7 puts Caddy in front of it for HTTPS, and Caddy
is the only thing other devices should be able to reach directly. `--proxy-headers
--forwarded-allow-ips=127.0.0.1` is what lets the app still see each *device's* real IP address
once every request is arriving via Caddy's own loopback connection — see step 7 for why that
matters.)*

## 6. Make it run automatically (so it survives a reboot, without a terminal window open)

The simplest reliable way on Windows, with nothing extra to install, is **Task Scheduler**:

1. Open **Task Scheduler** (search for it in the Start menu).
2. **Create Task** (not "Create Basic Task" — the full dialog gives more control).
3. **General tab:** name it `CableLIMS`. Tick **"Run whether user is logged on or not"**. Tick
   **"Run with highest privileges"**.
4. **Triggers tab → New:** Begin the task **"At startup"**.
5. **Actions tab → New:**
   - Program/script: `C:\CableLIMS\cablelims\backend\venv\Scripts\python.exe`
     (use the actual path you copied things to)
   - Arguments: `-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1`
   - Start in: `C:\CableLIMS\cablelims\backend`
6. **Settings tab:** tick **"Restart the task if it fails"**, every **1 minute**, up to a high
   attempt count (so a crash doesn't take the lab down until someone notices).
7. Save it, then right-click the task → **Run**, to start it immediately without waiting for a
   reboot.

Test again from a browser on the server (`http://localhost:8000`) to confirm it's alive under
the scheduled task, not just when you ran it manually.

## 7. Add HTTPS (Caddy)

Without this, usernames, passwords, and every bearer token cross the lab Wi-Fi in plain text —
anyone with a Wi-Fi sniffer on the same network can read them. Caddy sits in front of the app as a
reverse proxy and handles all of this; the app itself doesn't need to know or care that it's
behind one.

**Why Caddy, and why its own local certificate authority rather than a "real" one:** this server
has a private LAN IP, not a public domain name, so a publicly-trusted certificate (the kind a
browser trusts with no warning, e.g. Let's Encrypt) isn't obtainable — those require proving
control of a public domain. Caddy's own local CA (`tls internal` in the Caddyfile) is the standard
answer for exactly this shape of deployment: a small, known set of devices on a private network.
The one real cost is that each of those devices needs Caddy's root certificate installed once,
covered in step 7.4 below — after that, HTTPS just works with no more prompts.

1. **Download Caddy.** Go to https://caddyserver.com/download, pick **Windows / amd64**, download
   the `.zip`, and extract `caddy.exe` to a folder of its own, e.g. `C:\CableLIMS\caddy\`.
2. **Copy the Caddyfile.** This project ships one at `cablelims\deploy\Caddyfile` — copy it next
   to `caddy.exe`. Open it and replace the placeholder `192.168.1.50` (it appears twice) with this
   server's actual address from step 1's `ipconfig` lookup — the same static IP/DHCP reservation
   you already arranged.
3. **Test it once, manually.** In `C:\CableLIMS\caddy\`:
   ```
   caddy.exe run
   ```
   On the server, open a browser to `https://localhost` (no `:8000` — Caddy listens on the
   standard HTTPS port, 443). The first time, your browser will likely warn that the certificate
   isn't trusted yet — that's expected until step 7.4. If the page loads (past the warning), it's
   working; press `Ctrl+C` to stop it.
4. **Trust Caddy's certificate on each lab device.** After Caddy has run at least once, its local
   root certificate is at
   `%LOCALAPPDATA%\Caddy\pki\authorities\local\root.crt` on the server. Copy that one file to each
   device that will use CableLIMS (e.g. via a shared drive, email to yourself, or a USB stick), and
   install it as a trusted root certificate:
   - **Windows (the Scientist's desktop):** double-click `root.crt` → **Install Certificate** →
     **Local Machine** → **Place all certificates in the following store** → **Trusted Root
     Certification Authorities**.
   - **Android (Scientific Assistants' phones):** Settings → Security → **Install a certificate**
     (or **Encryption & credentials → Install a certificate**) → **CA certificate** → pick the
     file.
   - **iOS:** AirDrop or email the file to the phone, open it (Settings prompts to install a
     profile), then **Settings → General → VPN & Device Management** to finish, then **Settings →
     General → About → Certificate Trust Settings** and enable full trust for it — iOS installs a
     custom root as untrusted-for-websites by default until this last step.

   This is a one-time step per device — do it once when the device is set up, not every time
   someone opens the app.
5. **Make Caddy run automatically**, the same way as step 6 above — a second Task Scheduler entry:
   General tab name `CableLIMS-Caddy`, same "run whether logged on or not" / "highest privileges"
   settings, Trigger "At startup", Action Program/script
   `C:\CableLIMS\caddy\caddy.exe`, Arguments `run --config C:\CableLIMS\caddy\Caddyfile`,
   Start in `C:\CableLIMS\caddy`, same restart-on-failure settings.

## 8. Let other devices on the lab network reach it

1. **Find the server's local IP address**, if you haven't already (step 7.2 needed it too). On the
   server, open Command Prompt and run `ipconfig` — look for "IPv4 Address" (something like
   `192.168.1.50`). Ask whoever manages CTL's network to give this machine a **static IP or a DHCP
   reservation**, so this address never changes — otherwise everyone's saved bookmark breaks the
   next time the server reboots.
2. **Allow Caddy's ports through the Windows firewall — not port 8000.** The app itself
   (`127.0.0.1:8000`, step 5) is no longer reachable from the network at all, by design; only
   Caddy is. Windows Security → Firewall & network protection → Advanced settings → Inbound Rules
   → New Rule → Port → TCP → Specific ports `443,80` → Allow the connection → tick all three
   profiles (Domain, Private, Public) → name it `CableLIMS-HTTPS`. (Port 80 is only used to
   redirect to 443 — see the Caddyfile.)
3. From any other device on the same network (a phone, another PC) that has already trusted
   Caddy's certificate (step 7.4), open `https://<that IP address>` — e.g. `https://192.168.1.50`.
   That's the address everyone uses. Consider printing it on a small label near the lab bench for
   the Scientific Assistants' phones, and having the Scientist bookmark it on the desktop.

## 9. Before this goes in front of real samples

If you followed section 4 above (`--config-only` + `create_user`), there is nothing to do here —
there never were any demo accounts or demo samples on this install, and there's no
`CABLELIMS_ALLOW_DEMO_USERS` variable set on this machine, so the bare `python -m app.seed`
command (if anyone ever runs it out of habit) does nothing beyond re-confirming the standard/test
configuration. **Do not set `CABLELIMS_ALLOW_DEMO_USERS=1` on this server, ever** — that variable
exists only for internal development machines.

If this install was instead set up with the old demo-account instructions, or you're not sure:
check under **Administration → Users** (log in as an Administrator) for any account named
`scientist1`, `assistant1`, or `admin1` with `is_demo` set — deactivate or delete those and
create real named accounts via `app.create_user` or the Administration screen instead. Then
decide whether to keep or wipe the seeded demo samples (`SMP-2026-0009`, `SMP-2026-0011`): to
wipe everything and start empty, stop the scheduled task, delete `backend\data\cablelims.db`
(and any `.db-shm` / `.db-wal` files next to it), then re-run
`venv\Scripts\python -m app.seed --config-only` to recreate just the standard/test configuration
with no sample data.

## 10. Backing it up

**Do not just copy `cablelims.db` in File Explorer.** The database runs in a mode (WAL) where
recently-saved changes can sit in a companion `cablelims.db-wal` file for a while before being
folded into the main file — a plain copy of `cablelims.db` alone, taken while the app is running,
can silently miss recent samples/readings, or catch the file mid-write and produce something
unreadable. This is the single most important correction in this whole guide: a backup you have
never restored, taken the wrong way, can fail you at exactly the moment you need it.

**Use `backup_now.bat` instead** (in the same folder as `start_cablelims.bat`) — safe to run while
the app is running, because it uses SQLite's own online-backup mechanism rather than a plain file
copy. It also backs up the generated certificates in `certificates\` and the uploaded
marking/diagram photos in `uploads\`, which the old instruction omitted. Each run creates a
timestamped folder under `cablelims\backend\backups\`, verifies the database copy is actually
readable before calling the backup complete, and automatically keeps only the 30 most recent runs
so this doesn't grow forever.

1. **Set it up as a nightly Task Scheduler job**, the same way you set up `start_cablelims.bat` in
   step 6 — Action: Program/script `C:\CableLIMS\cablelims\backend\venv\Scripts\python.exe`,
   Arguments `-m app.backup`, Start in `C:\CableLIMS\cablelims\backend`, Trigger: daily, at a quiet
   time (e.g. 2 AM).
2. **Point it somewhere that isn't this machine's disk**, if at all possible — a network drive or
   external disk, passed as an argument: Arguments `-m app.backup D:\CableLIMS-Backups`. A backup
   sitting on the same disk as the original protects against accidental deletion or a corrupted
   database, but not against this machine failing outright.
3. **Actually restore one, once, so you know the procedure works before you ever need it under
   pressure.** Pick a recent backup folder under `backend\backups\` (or your network destination).
   Stop the scheduled CableLIMS task. Rename the current `backend\data\cablelims.db` (don't delete
   it) rather than overwriting it directly. Copy the backup's `cablelims.db` into `backend\data\`,
   and its `certificates\`/`uploads\` folders into `backend\` the same way. Restart the task and
   confirm the samples you expect are there. Put the date you did this drill, and who did it,
   somewhere you'll find it again.

## 11. If something's not working

- **Can't reach it from another device, but `localhost` works on the server:** almost always the
  firewall rule (step 8.2) — double-check it, and check the server's IP hasn't changed (step 8.1).
- **Devices see "Your connection isn't private" / a certificate warning:** that device hasn't
  trusted Caddy's certificate yet — see step 7.4. Until then this is expected, not a sign
  something's broken; the connection is still genuinely encrypted, the browser just doesn't
  recognize the certificate's issuer.
- **`caddy.exe run` fails to start, or another device still can't reach it over HTTPS even after
  trusting the certificate:** check the Caddyfile's two placeholder addresses (step 7.2) actually
  match this server's real IP — a typo there means Caddy is listening for the wrong address.
- **Page loads but looks broken / blank:** the `frontend\dist` folder is probably missing or in
  the wrong place — it must be at `cablelims\frontend\dist` (see step 3).
- **Task Scheduler shows the task "Running" but nothing responds:** check that the account the
  task runs as has permission to write to `cablelims\backend\data\` and `certificates\` — this
  is the most common Task Scheduler + "run whether user is logged on or not" gotcha.
- **Something went wrong and you need to know what:** check
  `cablelims\backend\logs\cablelims.log` — every request is recorded there (including under Task
  Scheduler, where there's no console window to show it), and any unexpected error is logged with
  full detail, timestamped, so you can match it to roughly when a Scientist says something broke.
  The file rotates automatically once it grows past 5 MB, keeping the last 5.
