# CableLIMS — MVP Demonstration Build

A working demonstration of the CableLIMS vision: Scientist desktop console + Scientific Assistant
mobile workflow, a real rule/confidence engine, and PDF certificate generation — scoped to the
Cable product family under IS 694, per `CableLIMS_SDD_v2.md` and `CableLIMS_Roadmap_v2.md`.

**What's real vs. placeholder:** Conductor resistance (IS 8130 Table 2 + Table 6), insulation
thickness (IS 694 Table 5), and the qualitative fire/HV tests are backed by verified BIS values
(see `backend/app/services/skb_seed_data.py` — every number is tagged VERIFIED with its exact
clause/table citation). Tensile/elongation limits are explicitly tagged PLACEHOLDER (IS 5831's
source scan is OCR-degraded — see the SDD). Insulation resistance has **no** limit at all, on
purpose — it demonstrates the "never guess" principle producing an honest UNDETERMINED rather
than a fabricated number.

## Running it for the demo

You need two terminals.

**Terminal 1 — backend:**
```
cd cablelims/backend
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
(Deliberately no `--reload` — it proved unreliable during development on this machine, silently
serving stale code after a file change without visibly failing. If you edit backend code, stop
this process fully (Ctrl+C, confirm no leftover `python.exe` in Task Manager) and start it again.)
(First time only, or to reset to clean demo data: `venv\Scripts\python -m app.seed` — safe to
re-run, wipes nothing but adds nothing twice. To fully reset: delete `backend/data/cablelims.db*`
and `backend/certificates/*.pdf`, then re-run the seed command.)

**Terminal 2 — frontend:**
```
cd cablelims/frontend
npm run dev
```
Open **http://localhost:5173** for the Scientist desktop console (best in a normal browser
window, maximized). The terminal also prints a **Network** URL (e.g.
`http://192.168.x.x:5173`) — open that same URL on a phone connected to the same Wi-Fi/LAN to
demo the Scientific Assistant mobile experience for real, including camera capture.

## Demo accounts (password `demo1234` for all)

| Username | Role | Use for |
|---|---|---|
| `scientist1` | Scientist | Desktop console — register samples, review, approve, generate certificates |
| `assistant1` | Scientific Assistant | Phone — profile capture, test entry |
| `admin1` | Administrator | Exists for the role model; no dedicated screens in this MVP |

## Suggested walkthrough (under 5 minutes)

1. **Log in as `scientist1`** on desktop. Dashboard shows two pre-seeded samples (one archived
   with a certificate already issued, one mid-testing) so it doesn't look empty on first login.
2. **Register Sample** — pick IS 694, leave cores/CSA at the sensible defaults (3 core, 2.5 mm²
   — this exact CSA has verified BIS data), assign it to `assistant1`, create it.
3. **Switch to a phone** (or a second browser window) and **log in as `assistant1`**. The new
   sample appears in "My Samples."
4. Open it → **photograph the marking** (or skip) → fill the profile (try **Fire Category =
   FR-LSH** — this is the scenario that pulls in the fire-performance tests and produces the
   richest System Decision panel) → **Confirm Profile & Assign Tests**.
5. Enter readings for each assigned test. Suggested values that reproduce a realistic,
   varied outcome (verified PASS, a real borderline UNDETERMINED, and placeholder/missing
   UNDETERMINED):
   - Conductor Resistance: 7.28 ohm/km @ 27°C
   - Insulation Thickness: 0.82, 0.81, 0.85, 0.80, 0.83 mm
   - Tensile: 210 N, 10mm width, 1.6mm thickness
   - Elongation: 25mm → 68mm
   - High Voltage: no breakdown
   - Insulation Resistance: 145 M-ohm
   - Spark Test: no spark
   - Oxygen Index: 29.3% (deliberately just above the 29.0% verified limit — triggers the
     guard-band "borderline, needs Scientist judgement" path)
   - Halogen Acid Gas: 12.4%
   - Temperature Index: 262°C
6. **Switch back to the Scientist desktop.** Open the sample — the **System Decision panel**
   updates live, showing the confidence score and exactly which tests need Scientist attention
   and why (placeholder limit / no criterion yet / borderline result — each is labelled
   differently, not lumped together).
7. **Approve**, then **Generate Certificate**, then **Download Certificate** — a professional
   PDF with a QR code, full test table, and the overall decision.

## Architecture notes for anyone reading the code

- `backend/app/services/standards_service.py` + `skb_seed_data.py` — the entire Standards
  Knowledge Base placeholder. This is the one module a real SKB integration would replace;
  every caller goes through its `LookupResult` contract (VERIFIED/PLACEHOLDER/MISSING), so
  nothing else in the app needs to change.
- `backend/app/engines/` — rule engine, calculation engine, confidence engine, report engine.
  Each is plain Python, independently testable, and reads configuration from the database
  rather than hardcoding standard-specific logic.
- `backend/app/services/ocr_service.py` — stub only, by design (see `CableLIMS_SDD_v2.md`
  section 6.6). The Scientific Assistant photographs the marking; a human still reads and
  enters it.
- Full architecture reasoning, the verified BIS standards catalog, and the production roadmap
  (multi-product-family support, offline sync, calibration tracking, etc.) live in
  `CableLIMS_SDD_v2.md` and `CableLIMS_Roadmap_v2.md` at the project root.
