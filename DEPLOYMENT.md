# CableLIMS — Installing on CTL's Server

This guide assumes a Windows machine on CTL's own local network, set up by someone comfortable
with basic Windows administration (installing software, using Task Scheduler, allowing an app
through the firewall) but not necessarily a software developer. No AI assistance is needed to
follow it.

**What you end up with:** one program running quietly in the background on the server. Everyone
on the lab's network — the Scientist's desktop, Scientific Assistants' phones — opens a web
address pointed at that server. Nothing is installed on the phones; they just use their browser.

---

## 1. What the server needs installed

- **Python 3.12 or later.** Download the official installer from https://www.python.org/downloads/
  — during install, tick **"Add python.exe to PATH"**.
- **Node.js is NOT required on the server.** It's only needed once, to produce the website files
  — you can do that step on any other computer (e.g. the machine this was built on) and copy the
  result over. See step 3.

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
section 8.)*

**Optional: adjust configuration.** `backend\.env.example` lists every operational setting the app
reads (session length, upload size limit, log rotation, backup retention, and more) with its
default and a description. Most installs never need to touch this — the defaults are sane for a
single lab. To change one, copy `.env.example` to `.env` in the same `backend` folder, uncomment
the line(s) you want to change, and restart the app (step 6). Never commit or hand out a real
`.env` file if it ever contains anything sensitive.

## 5. Test it once, manually

Still in `cablelims\backend`:
```
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
On the server itself, open a browser to `http://localhost:8000` — you should see the CableLIMS
login page. If that works, press `Ctrl+C` to stop it, and move on to making it run permanently.

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
   - Arguments: `-m uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Start in: `C:\CableLIMS\cablelims\backend`
6. **Settings tab:** tick **"Restart the task if it fails"**, every **1 minute**, up to a high
   attempt count (so a crash doesn't take the lab down until someone notices).
7. Save it, then right-click the task → **Run**, to start it immediately without waiting for a
   reboot.

Test again from a browser on the server (`http://localhost:8000`) to confirm it's alive under
the scheduled task, not just when you ran it manually.

## 7. Let other devices on the lab network reach it

1. **Find the server's local IP address.** On the server, open Command Prompt and run
   `ipconfig` — look for "IPv4 Address" (something like `192.168.1.50`). Ask whoever manages
   CTL's network to give this machine a **static IP or a DHCP reservation**, so this address
   never changes — otherwise everyone's saved bookmark breaks the next time the server reboots.
2. **Allow the port through the Windows firewall.** Windows Security → Firewall & network
   protection → Advanced settings → Inbound Rules → New Rule → Port → TCP → Specific port
   `8000` → Allow the connection → tick all three profiles (Domain, Private, Public) → name it
   `CableLIMS`.
3. From any other device on the same network (a phone, another PC), open
   `http://<that IP address>:8000` — e.g. `http://192.168.1.50:8000`. That's the address
   everyone uses. Consider printing it on a small label near the lab bench for the Scientific
   Assistants' phones, and having the Scientist bookmark it on the desktop.

*(Optional polish: if you want to drop the `:8000` and just use a plain address, running it on
port `80` instead does that — change `--port 8000` to `--port 80` everywhere above and open port
80 in the firewall instead. Port 80 sometimes needs the task to run as Administrator, which
"Run with highest privileges" in step 6 already covers.)*

## 8. Before this goes in front of real samples

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

## 9. Backing it up

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

## 10. If something's not working

- **Can't reach it from another device, but `localhost` works on the server:** almost always the
  firewall rule (step 7.2) — double-check it, and check the server's IP hasn't changed (step 7.1).
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
