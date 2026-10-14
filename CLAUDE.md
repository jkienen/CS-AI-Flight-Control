# Claude Code Instructions

## Skill

This repository is run by [`Review.md`](Review.md). At the start of every session, read it and follow its "0. Session start" steps before anything else: confirm that `Input/CIDs.csv` is a fresh export from the CrowdStrike console, then render the structure.

- Every run writes to today's folder, `Output/YYYY-MM-DD/`. Never change or delete the folders of earlier days: they are the history of each review.
- Corrections go into today's `CIDs_Expected.csv` only. Never edit `CIDs.html` or `Case_Message.txt` by hand: run `Output/Scripts/Generate-FlightControl.py` again.
- Change the generator only to change how the graph or the case text looks or behaves, never because of the data. Keep its code organization (the `Part N` sections, 2-space indentation, f-strings) and update the matching section of `Review.md`.
- Write `Review.md` and everything in `Output/` in English. Talk to the user in their language.

## File Access Restrictions

Do NOT read, open, or inspect the following file types:
- `*.env` (contains secrets/credentials)

If a task needs a value from one of them, ask the user instead.
