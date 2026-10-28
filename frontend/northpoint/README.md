# Northpoint frontend

The current frontend is connected to **https://cs317.duckdns.org/app1** using the supplied API-INTEGRATION.md and APIREFERHERE.txt contracts. Employees, Add/Edit Employee, profiles, employee status/delete, violations, rulebook, dashboard, reports, History and Calendar use backend requests. The version label remains `v.FE-1.0`; the existing desktop/phone layout and simplified footer are retained.

## Open the website

Open the built **index.html** in your browser while connected to the internet. **npm, Docker and a local backend are not required to use the bundled page.** The browser must permit the hosted API's CORS response for its origin. All styles, fonts and images are bundled in the page.

If you prefer serving the frontend over HTTP and have Node installed, `node serve.mjs` (or `npm start`) serves only the HTML at **http://localhost:4173/**. API requests still go directly to the hosted backend. For another port, set PORT. For a phone on the same network, set HOST to `0.0.0.0` and open the computer's LAN IP on that port. Restart the server after rebuilding.

Set **Your display name** in Settings before making changes. The documented write endpoints use it as X-Actor, and violation removal uses it as removed_by. No default person is assigned. Workspace role choices are local view filters, not authenticated account roles. Users & Roles remains Coming Soon.

Loading, successful saves, validation/conflict/access errors, timeouts and lost responses are handled. Records are never stored locally or queued offline. No failed API request falls back to sample records. Unconfirmed saves use Check save status to read the backend before another write is allowed.

## Development checks

Node 24+ is needed only to rebuild or run these developer checks:

```powershell
node build.mjs
node verify.mjs
node --test
node tooling/check-live.mjs
```

The equivalent npm scripts are build, check, test and test:live. The live check makes GET/OPTIONS requests only; it never creates, edits or deletes company records. Automated write tests use synthetic responses through the real transport/adapters and generated UI handlers. Fixture modules are isolated to tests and excluded from the bundled website.

See **INTEGRATION.md** for the implemented endpoint map, error behavior and known backend limits. The two supplied API reference files are preserved as received.
