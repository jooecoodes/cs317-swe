# Northpoint UI preview

Static HTML, CSS and browser JavaScript for the Northpoint interface. This copy has no database, API transport, account service, Docker files, dependency installation, or browser record storage.

Open **index.html** directly in a browser. It includes its logo, fonts, styles, scripts and fictional examples, so internet access is unnecessary. The visible preview notice distinguishes these examples from company records.

Desktop and phone layouts retain the dashboard, employee directory and profiles, violations, rulebook, History tabs, reports, settings and help. Search, filters, ordering, pagination, disclosure cards, suggestions and form validation are interactive. Form submissions show a preview-only message and do not create, update or delete records. Preferences apply only to the open tab and reset on reload. Users & Roles remains Coming Soon.

Edit the modules in **src/**, then run `node build.mjs` to regenerate index.html. Node 24 or later is needed only for building and tests; it is unnecessary for opening the built page. Run `node --test tests/*.test.mjs` for checks.

For a phone, serve this directory with an existing static web server and open its address from the same network. When included in the backend repository's existing frontend directory, the UI is available at **/northpoint/** after the repository's normal sign-in. This PR does not change its login service.

See **INTEGRATION.md** for the data source contract and backend mapping. See **PR-NOTES.md** for the additive repository placement and conflict check.
