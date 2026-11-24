# Zone Scorecard

A single-page scorer for supply and demand zones. Six checks, 20 points, 14 or more is a valid setup. Entry waits for the retest of the zone.

The whole site is one file, `index.html`. There is no build step and no dependencies. Trade log data is saved in each visitor's own browser (localStorage), so nothing is sent to a server.

## Publish it with Claude Code

1. Put `index.html` and this `README.md` in a new folder called `zone-scorecard`.
2. Open a terminal in that folder and start Claude Code.
3. Paste this prompt:

```
This folder is a static website (index.html, no build step). Do the following:
1. Initialize a git repo and commit the files.
2. Create a public GitHub repo named zone-scorecard with the gh CLI and push to it.
3. Deploy it as a static site on Vercel (framework preset: Other, no build command, output directory: the repo root) and give me the live URL.
If gh or vercel is not logged in, tell me the exact command to run and wait.
```

4. Open the live URL it gives you and test it on your phone.

## Other ways to host it

- **GitHub Pages:** push the repo, then go to the repo's Settings, Pages, choose the `main` branch and the `/ (root)` folder, and save. The site appears at `https://YOUR-USERNAME.github.io/zone-scorecard/` within a minute or two.
- **Netlify Drop:** go to app.netlify.com/drop and drag the folder onto the page. No account setup or git needed.
- **Custom domain:** add it in the host's domain settings (Vercel, Netlify or GitHub Pages), then point your DNS records where the host tells you.

## Change the rules later

Scoring lives at the top of the script in `index.html`: the `PASS` score, the `CHECKS` list (questions and points) and the `PRESETS` timeframes. Ask Claude Code to edit those, then push again. Vercel and GitHub Pages redeploy on every push.

## Hourly scanner (Setups board)

The Jay S&D indicator scores its two target zones itself on every bar close and can post the result to this site. The board at `/setups.html` shows the latest report per symbol and side and marks anything at or above the indicator's Valid Setup Score.

One-time setup:

1. **Store.** In the Vercel project open Storage, Create Database, pick Upstash Redis and connect it to the project. That adds `KV_REST_API_URL` and `KV_REST_API_TOKEN` automatically.
2. **Sender check.** By default the webhook accepts only TradingView's published webhook addresses, so no secret is needed. To use a key instead, add `SCAN_SECRET` with `vercel env add SCAN_SECRET production`, redeploy, and append `?key=SCAN_SECRET` to the webhook URL.
3. **Alerts.** For each symbol, on a 1H chart with Jay S&D on it: create an alert, condition Jay S&D then Any alert() function call, Once per bar close, webhook URL `https://zone-scorecard.vercel.app/api/setup-alert`.

Endpoints: `POST /api/setup-alert?key=...` receives the alert JSON; `GET /api/setups` lists the latest reports.

The indicator's Trading Style setting (Scalping 5m / 30m / 1H, Scalping 5m / 15m / 1H, Day Trading 1H / 4H / D, Swing Trading 4H / D / W, Longer Swing D / W / M, Custom) picks the Low, Mid and High timeframes and matches the presets on the sheet.
