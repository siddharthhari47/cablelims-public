# Running CableLIMS on your PC

## First-time setup (do this once)

1. Copy the whole `cablelims` folder from the drive onto your PC — anywhere is fine, e.g.
   `C:\CableLIMS\cablelims`.
2. If you don't already have Python installed: download and install it from
   **https://www.python.org/downloads/** (Python 3.12 or newer). During installation, make sure
   you tick **"Add python.exe to PATH"** — it's a checkbox on the first screen.
3. Double-click **`first_time_setup.bat`** inside the `cablelims` folder. It will:
   - set itself up (a minute or two, downloading nothing except from your own PC's Python)
   - ask you to create your own login — a username, your name, your role, and a password you
     choose. **There are no default passwords on this install** — this is the only account
     that exists until you create more the same way.
4. When it says "Setup complete," double-click **`start_cablelims.bat`**.
5. A black window opens and stays open — that's the app running. Leave it open (you can
   minimize it) while you're using CableLIMS; closing that window stops the app.
6. Open a browser to **http://localhost:8000** and log in with the account you just created.

## Using it from a phone (optional)

If you want to try the mobile side of the app (the Scientific Assistant screens), the phone
needs to be on the **same Wi-Fi network** as this PC:
1. With the app running, open Command Prompt and type `ipconfig`, look for "IPv4 Address"
   (something like `192.168.1.50`).
2. On the phone's browser, go to `http://<that address>:8000` — e.g. `http://192.168.1.50:8000`.
3. If it doesn't connect, Windows Firewall is the most likely reason — see the "Firewall" note
   in `DEPLOYMENT.md` in this same folder for the two-minute fix.

## Adding more logins later

Run `first_time_setup.bat` again any time — it's safe to re-run, and running it again just lets
you create another account (or reset a password, if you use the same username again). It won't
touch or delete any samples you've already entered.

## Everyday use

Just double-click `start_cablelims.bat` whenever you want to use it, and close that window when
you're done. Nothing needs reinstalling — the setup step is genuinely one-time.

## Receiving updates

When an update arrives, see `UPDATING.md` in this same folder — it's a two-minute process and
your existing samples and certificates are never affected by it.

## Where your data lives (for your own peace of mind / backups)

Everything you create — samples, test results, certificates — lives in one place:
`cablelims\backend\data\cablelims.db`, plus the generated PDF certificates in
`cablelims\backend\certificates\`. Nothing about this app ever sends anything over the internet
— it only talks to itself and to devices on your own network. If you want a backup, copying
those two locations somewhere safe (a USB drive, a network folder) is all you need.
