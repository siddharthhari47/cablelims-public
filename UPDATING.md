# Applying an update

When you receive a new `cablelims_*.zip`, this replaces the **app itself** — never your samples,
certificates, or login. Those live in a separate folder that updates never touch.

## Steps

1. **Close the app first.** If `start_cablelims.bat`'s black window is open, close it.
2. **Rename your current folder** as a safety net — e.g. `cablelims` → `cablelims_old`. (You can
   delete `cablelims_old` once you've confirmed the update works, or just keep it a while.)
3. **Unzip the new package** so you end up with a fresh `cablelims` folder in the same place as
   before.
4. **Copy your data across** from the old folder into the new one — this is the one manual step,
   and it's the only thing that matters:
   - Copy `cablelims_old\backend\data\` → `cablelims\backend\data\` (replace/merge)
   - Copy `cablelims_old\backend\certificates\` → `cablelims\backend\certificates\` (replace/merge)
   - Copy `cablelims_old\backend\uploads\` → `cablelims\backend\uploads\` (replace/merge, if it
     exists)
5. Double-click **`first_time_setup.bat`** in the new folder — it reinstalls the Python
   environment for the updated code. When it gets to the "create your login" step, you can
   safely press Ctrl+C to skip it — your existing login came across with the data folder in
   step 4 and still works.
6. Double-click **`start_cablelims.bat`** as usual and confirm your samples are all still there.

## Why it's built this way

The update package never contains a `data` folder at all — only app code and the compiled
website. That's deliberate: it makes it structurally impossible for an update to silently
overwrite anything you've entered, because there's nothing data-related in the zip to overwrite
with. The one manual copy step in #4 is the tradeoff for that safety, and it's the same three
folders every time.

If anything looks wrong after an update, your renamed `cablelims_old` folder from step 2 is a
complete, working fallback — start it up instead while we sort out the issue.
