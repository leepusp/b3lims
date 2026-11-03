# B3 LIMS: ELN, calendar and registry checklist

Working list agreed with the lab. Each block must be finished, tested and deployed
before the next one starts. `[x]` done and live, `[~]` done, waiting for deploy,
`[ ]` open.

## Block A: finish ELN 2.2 (do this before anything else)

- [x] Advanced search (`title:gel and status:completed`, `extrafield:Medium:TSB`)
- [~] Sharing: read / edit / manage grants for users and research groups (no migration)
- [ ] "Shared with me" filter in the entries dashboard
- [ ] Ownership transfer (author to another user; grants and revisions stay)
- [ ] Categories and statuses per research group, with colours (migration; replaces the fixed lists)
- [ ] Editable entry templates (stored in the database, not in code)
- [ ] Favourite tags panel and step groups
- [ ] Field builder / JSON editor for extra fields
- [ ] Browser check of all of the above on production

## Block B: Lab Calendar (new, runs on the existing `bench` Booking models)

Today `/calendar/` only lists the last 100 sample events. It becomes a real calendar.

Foundation
- [ ] Month, week and agenda views (FullCalendar 6, MIT, vendored with checksums)
- [ ] Layers with colours and filters: bookings, ELN step deadlines and to-dos,
      shipments, sample reminders, lab meetings
- [ ] Create, move and resize bookings in the calendar, with conflict detection
      and the existing resource rules
- [ ] Recurring events (daily, weekly, custom) and per-event reminders
- [ ] Attendees with accept / decline, and a link from an event to an ELN entry
- [ ] Dashboard card "Today and this week" (closes the "bookings" gap in the ELN dashboard)

Google Calendar
- [ ] Step 1, no credentials needed: per-user private `.ics` feed, with a token that can be
      renewed or revoked, to subscribe from Google Calendar ("From URL").
      Needs the LIMS address to be reachable from Google's servers, and Google
      refreshes subscribed feeds only every several hours.
- [ ] Step 1: "Add to Google Calendar" button and `.ics` download on every event
- [ ] Step 2, needs a Google Cloud OAuth client created by the lab: push LIMS events
      to the user's Google Calendar and keep them updated or removed; optional read of
      busy times to avoid booking conflicts. Tokens stored encrypted, one-click disconnect.
- [ ] Export of any calendar view (`.ics`, CSV)

Other useful functions
- [ ] Equipment calendar per resource, with usage report (hours per user and per group)
- [ ] Booking approval for restricted equipment, and e-mail notification
- [ ] "Find a free slot" for a resource and for a group of people
- [ ] Booking templates for common runs (sequencing, qPCR, culture passages)

## Block C: ELN 2.3 to 2.6 (see `eln_elabftw_parity.md`)

- [ ] 2.3 resources, storage on entry
- [ ] 2.4 Ketcher, PubChem, 3D viewer, drawing
- [ ] 2.5 lock, signatures, RFC 3161 timestamps, audit, request actions, notifications
- [ ] 2.6 exports (PDF, `.eln`, CSV, ZIP, QR), imports, REST API with keys

## Block D: Molecular Registry rework

- [ ] Map what the Registry does today and where each OpenCloning module fits
      (cloning, primers, description, sequence, data model, settings)
- [ ] Implement the OpenCloning-style structures in the Registry
- [ ] Clean up the old structures

## Block E: workflows and submissions

- [ ] Tools and workflow builders (Jupyter / Slurm, Galaxy)
- [ ] Submissions: ENA, NCBI, Zenodo

## Housekeeping

- [ ] Remove old `static-releases` (keep live, rollback and the two latest)
- [ ] `notebook.py` still holds the Molecular Registry views; split it during Block D
