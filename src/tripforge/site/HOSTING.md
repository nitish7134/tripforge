# Hosting a tripforge site

One static folder + one tiny Python service behind Caddy. Nothing is served without the PIN cookie; the backend checks the PIN
(rate-limited, HttpOnly cookie for a year) and owns the shared ledger. Replace `<slug>`, `<port>`, `<pin>`.

## 1. Files
```
sudo mkdir -p /var/www/<slug>/data /var/lib/<slug>ledger /etc/flightwatch /opt/tripledger /opt/flightwatch
sudo cp -r trips/<slug>/site/dist/. /var/www/<slug>/          # index.html sw.js manifest icon lock/ img/ data/
sudo install -m 755 src/tripforge/site/server/tripledger.py /opt/tripledger/tripledger.py
sudo install -m 755 src/tripforge/site/server/flightwatch.py /opt/flightwatch/flightwatch.py
sudo useradd -r -s /usr/sbin/nologin tripledger 2>/dev/null || true
sudo install -d -m 750 -o tripledger -g tripledger /var/lib/<slug>ledger
```

## 2. Ledger + PIN service (`/etc/<slug>ledger.env`, mode 600)
```
TRIP_PIN=<pin>
TRIP_TOKEN=<python3 -c "import secrets;print(secrets.token_urlsafe(24))">
# optional read-only visitor role:
# TRIP_PIN_RO=....  TRIP_TOKEN_RO=....
TRIP_COOKIE_PATH=/<slug>
TRIP_WHO=<who>
TRIP_CURS=<curs>
TRIP_PORT=<port>
```
systemd unit `/etc/systemd/system/<slug>ledger.service`:
```
[Unit]
Description=<slug> trip page: PIN gate + shared ledger API (loopback :<port>)
After=network-online.target
[Service]
EnvironmentFile=/etc/<slug>ledger.env
Environment=LEDGER_PATH=/var/lib/<slug>ledger/ledger.json
ExecStart=/usr/bin/python3 /opt/tripledger/tripledger.py
Restart=on-failure
User=tripledger
Group=tripledger
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/<slug>ledger
[Install]
WantedBy=multi-user.target
```
`sudo systemctl daemon-reload && sudo systemctl enable --now <slug>ledger`

## 3. Flight status (optional)
`/etc/flightwatch/<slug>.json`: `{"out": "/var/www/<slug>/data/flights.json", "flights": [{"id":"6E6693","dep":"2026-11-22T09:45:00+05:30","from":"NAG","to":"GOX","icao":"IGO6693"}]}`
A oneshot service + 10-minute timer running `flightwatch.py /etc/flightwatch/<slug>.json` (see the Goa trip for the unit files).
Gate/belt data needs a free AeroDataBox key in `/etc/flightwatch.env` as `RAPIDAPI_KEY=`; without it the keyless ADS-B fallback still shows airborne/not yet.

## 4. Caddy
Inside the site block that will serve it (handle blocks are exclusive, put these before any catch-all):
```
redir /<slug> /<slug>/ 301
handle_path /<slug>/* {
    root * /var/www/<slug>
    header >Permissions-Policy "geolocation=(self)"
    @unlock path /api/unlock
    handle @unlock { uri strip_prefix /api
        reverse_proxy http://127.0.0.1:<port> { header_up X-Real-IP {remote_host} } }
    @lockasset path /lock/*
    handle @lockasset { header Cache-Control "public, max-age=86400"
        file_server }
    @noauth not header_regexp Cookie "(^|;\s*)trip=(TRIP_TOKEN[|TRIP_TOKEN_RO])(;|$)"
    handle @noauth {
        @page path / /index.html
        handle @page { rewrite * /lock/index.html
            header Cache-Control "no-store"
            file_server }
        respond "locked" 401 }
    handle /api/* { uri strip_prefix /api
        reverse_proxy http://127.0.0.1:<port> { header_up X-Real-IP {remote_host} } }
    @static path *.jpg *.png *.svg *.webp
    header @static Cache-Control "private, max-age=86400"
    header ?Cache-Control "no-store"
    file_server
}
```
If the enclosing block sets a `Permissions-Policy` that blocks geolocation, scope that header to `not path /<slug>*`.
`sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy` (restart if `admin off`).

## 5. Verify
- `curl -s -o /dev/null -w '%{http_code}' https://HOST/<slug>/data/plans.json` -> 401
- POST `{"pin":"0000"}` to `/<slug>/api/unlock` -> 403; the right PIN -> 204 with a `Set-Cookie`
- with the cookie, `/<slug>/api/ledger` -> 200
- open the page on a phone: PIN once, then Trip / Money / Kit; a headless check at 390px should show no console errors.

## 6. Updating
Rebuild (`tripforge site build trips/<slug>`), copy `dist/` over, done: the service worker cache name is bumped on every build so phones pick the new page up on the next open. `data/plans.json` can be replaced alone without a page rebuild.
