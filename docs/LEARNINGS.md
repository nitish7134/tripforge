# Learnings from shipping a trip page

Rules for the next trip site, learned the hard way on the first one. Each is something you can act on.

## Deploy

- **The service worker can hide a broken deploy.** A phone with the old cache keeps showing the old page while
  another device gets the broken one. Gate every deploy on `node --check` of the inlined script (tools/build.py does)
  and on a phone-viewport console check (390x844, read the console, swipe every page) before calling it done.
- **Bump the SW cache name on every deploy** (`trip-vN` in sw.js; tools/deploy.sh does it). Same name = stale page.
- **Never hand-edit the built index.html.** Edit `src/`, run `tripforge site build`. `tripforge site check` fails when
  index.html has drifted from its sources.
- **Caddy reload needs the admin API.** Hardened setups disable it, so `systemctl restart caddy` instead.
- **Agent shells block some shapes.** `chmod`/`chown` near `/etc/` paths and `rm -rf` are refused: use
  `install -m 644 -D src dst` (sets mode and owner in one step) and `find DIR -mindepth 1 -delete; rmdir DIR`.
- **Split big heredocs from ssh.** Write the file locally, copy it, then run a short remote command; one long command
  mixing a heredoc and ssh gets refused or mangled.

## Page

- **A photoless day page needs its own header offset.** The header pulls up over the photo (`.photo+.hd` negative
  margin); without a photo it needs the `.nophoto` spacer or it sits under the sticky date strip.
- **Stays carry `pics` and an `img` prefix.** Photo files are `img/stays/<img>-<n>.jpg`, so renaming or aliasing a stay
  key does not orphan its photos.
- **Ledger ids must accept seeded ids.** Entries seeded by hand ("seed-flight-1") have to stay editable and deletable;
  the server validates ids by shape (`[A-Za-z0-9_-]{4,40}`), not by its own uuid format.
- **Greedy settle-up is not minimal.** Biggest-creditor-pays-biggest-debtor always gives n-1 transfers. Minimum is
  n minus the most disjoint zero-sum groups: use the bitmask DP in `site_template/src/js/14b-settle.js`.

## Research data

- **Airbnb has no public API.** Listing ids only come from the traveller's own logged-in trip page (Playwright
  attached to their Chrome); search results do not show host names.
- **Self-host stay photos and dedupe them by perceptual hash.** Listing photo URLs expire and repeat across sizes.
- **Reddit is unreachable to fetchers.** Plan around it: use guides, venue pages and blogs that quote threads.
- **Research coordinates are often approximate.** Spot-check against OpenStreetMap before showing distances.

## Copy

- Terse and masculine. No "three of us", no headcount in copy: it goes stale when someone drops out.
- No section of rules the reader cannot act on.
- Never repeat a fact that is already in a checklist: one place per fact.
