# Framefinder v2 — your free animation / Houdini job radar

Framefinder checks publicly accessible studio career pages and permitted job feeds **twice daily**, keeps one row per position with all *verified* sources, displays **pay / remote-hybrid-onsite / location**, and tracks **early hiring signals** from public news. Telegram is used for notifications. A static web dashboard runs on **GitHub Pages** — no paid server or Cloudflare needed.

## Step-by-step: publish it for the first time (beginner-friendly)

### 1. Sign up for GitHub (free)

Open https://github.com and create a free account if you don't have one. The dashboard and results will be publicly accessible on GitHub Pages. **Do not put a password, bot token, or personal data in your repository.**

### 2. Create a repository

1. Open https://github.com/new
2. **Repository name:** `framefinder`
3. Choose **Public** (free GitHub Pages works with public repositories; public means other people can see the source and jobs, but not your Telegram secrets).
4. Leave **Add README**, **.gitignore**, and **license** unchecked.
5. Click **Create repository**.

### 3. Upload all project files from the ZIP

1. Download and extract `framefinder-v2.zip`.
2. Open the extracted `framefinder` folder, containing `README.md`, `jobwatch`, `site`, and `.github`.
3. **Important:** GitHub's browser upload might ignore hidden folders like `.github`. The most reliable path is **GitHub Desktop**: https://desktop.github.com/.
4. Install GitHub Desktop and sign in. Choose **File → Add local repository → Choose** your extracted `framefinder` directory. If prompted, choose **Create a repository here**.
5. Commit all files. Click **Publish repository** and select your new GitHub repo. If it already exists remotely, use **Repository → Repository settings → Remote** to configure the URL, or follow the command-line method below.

**Alternative, precise terminal instructions (recommended if GitHub Desktop won't publish into your existing empty repo):** install [Git for Windows](https://git-scm.com/downloads/win) (or Git on Mac), open a terminal in the **inner `framefinder` folder**, then run:

```bash
git init
git add .
git commit -m "Set up Framefinder v2"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/framefinder.git
git push -u origin main
```

Replace `YOUR_GITHUB_USERNAME`. GitHub may ask you to sign in through your browser. The top level of the repository must contain `site/`, `config/`, `jobwatch/`, and `.github/` — **not another wrapping folder**.

### 4. Activate the free web dashboard

1. In the `framefinder` repository, click **Settings** (top menu).
2. In the left sidebar, open **Pages**.
3. Under **Build and deployment → Source**, choose **GitHub Actions**. No template or custom domain is needed.
4. Your future site will be `https://YOUR_GITHUB_USERNAME.github.io/framefinder/`.

This is a public site without a login. Saved / Applied / Hidden choices stay locally in each browser, not across devices.

### 5. Set up Telegram notifications

1. Install Telegram or visit https://web.telegram.org and sign in.
2. Search for **@BotFather** (the official verified bot). Send `/newbot`. Give your bot a display name and username ending in `bot`.
3. BotFather gives you a long **token**. Do **not** post it in the GitHub repository or share it publicly.
4. Open your new bot in Telegram. Send `/start` and then `hello`.
5. In your browser, open `https://api.telegram.org/botPASTE_YOUR_TOKEN_HERE/getUpdates`. Look in the response for `"chat":{"id":123456789, ...}`. The number is your **chat ID**. If `result` is empty, send another message to your bot and refresh. This URL contains your private token; don't share it.
6. In GitHub, open **Settings → Secrets and variables → Actions**. Click **New repository secret** and add:
   - Name: `TELEGRAM_BOT_TOKEN` / Value: the long token
   - Name: `TELEGRAM_CHAT_ID` / Value: the numeric chat ID

Telegram notifications are optional. Without the secrets, job scanning and the website still work, but you receive no Telegram alerts.

### 6. Run it for the first time

1. In GitHub click **Actions**.
2. Choose **Framefinder — Search and publish** (left).
3. Click **Run workflow → Run workflow**.
4. Once the check finishes successfully, open your GitHub Pages URL from step 4. Refresh to see the matches.
5. Open **Source health** on the website to see whether any site blocked the check or changed its layout.

After this, GitHub Actions checks at **8:12 AM and 6:12 PM Vancouver time every day** (daylight saving is handled). GitHub may occasionally delay scheduled workflows. **GitHub may disable scheduled workflows on public repositories after 60 days without repository activity**; if it does, re-enable from the Actions tab. This project commits scan data when it changes, but that is not a guarantee against inactivity disabling.

## What each tab shows

- **Discover:** one row per unique role/company, sorted by match score. Pay, arrangement, location, and verified advertising sources are visible side by side. Multiple listings from several websites collapse into **one job with multiple source buttons**. Example: Official | Remotive — but those buttons only appear if the feed actually supplied that listing.
- **Early signals:** recent public production / recruitment news. A signal **is not an advertised vacancy** and may not lead to hiring. If you know someone at that studio, you can ask them directly. Alerts include an evidence link.
- **Needs verification:** unconfirmed animation assignment, unsupported Canadian remote eligibility, or ambiguous geography. Not automatically pushed as strong matches.
- **Saved / Applied / Hidden:** stored locally in the browser. They will not sync between your computer and phone.
- **Source health:** which studio boards responded and which need updated adapters. Failure is NOT evidence that the studio has no openings.

### LinkedIn and Indeed

The dashboard includes direct searches on [LinkedIn](https://www.linkedin.com/jobs/) and [Indeed](https://ca.indeed.com/). These are **search shortcuts, not automated scrapers**. Both services restrict unauthorized automated collection. The interface **never invents a LinkedIn or Indeed advertising badge**. Icons appear on a job only when a legitimate connected/authorized source actually provides the posting. The app currently has **no authorized LinkedIn or Indeed job-data integration**, so their badges will not appear on automatically discovered jobs. This is a limitation, not an implementation bug.

### Studio coverage

`config/sources.json` includes **45 configured sources** across Canadian 3D animation studios, remote-job feeds, and public production-news RSS. Initial direct boards include Netflix Animation, Disney Animation, Stellar, Mainframe, ICON, Arcana, Bardel, Atomic Cartoons, Sony Pictures Imageworks, WildBrain, Guru, Reel FX, Mercury Filmworks, Titmouse, Brown Bag Films, Jam Filled, Squeeze, Nelvana, 9 Story, Pipeline, Mikros, Cinesite Animation and others. **This is a wide discovery list, not every Canadian animation studio.** Some sites have no parseable vacancies, and Source health will expose them. Corporate rebrands, studio closures, and URL changes can make a configured source inactive.

For studios outside Vancouver, Framefinder only reports a strong match if working from Vancouver is permitted remotely. US remote jobs must accept Canada-based workers; if unclear, they are not automatically alerted. At mixed live-action/animation studios, an animated project must be established for a strong match.

### Salary and work arrangement

Salary is shown **only if the listing supplies a recognizable range**. `Not listed` means the feed didn't provide it, not that salary is zero. Arrangement is **Remote**, **Hybrid**, **On-site**, or **Not specified**, based on source wording; read the original posting before applying.

### Early signals are conservative leads

The job watcher reads public Google News RSS search feeds for animated-production launches, expansion, staffing, and similar indicators. A public announcement is **not confirmation of a vacancy**, and a broad news headline may still be irrelevant. Signals are labeled separately. Telegram alerts prioritize news about a newly announced production or staffing development in the last 14 days; they link to evidence. No automated direct messages are sent to people.

## Security and free-tier considerations

- The GitHub repo and Pages website are **public**. Do not store personally identifying details, resume files, contacts, or tokens in tracked files.
- Two scans/day usually fit free personal GitHub Actions usage, but availability and service limits may change.
- GitHub Pages is a free static site for public repositories; there's no private login or backend.
- **No live site has been deployed by ChatGPT.** You must create your repository, configure Pages and Telegram, and run the first scan.
- Access restrictions and JavaScript-heavy job boards can prevent discovery. No claim of complete coverage.
- Notifications require the bot secrets; if absent, they will remain pending as designed.
- Government, recruitment and employer policies can change. Source limitations are reflected in the UI.

## Developer quick checks

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m jobwatch
python -m http.server 8000 --directory site
```

Visit http://localhost:8000. For details of the collector see `jobwatch/core.py`. Edit `config/sources.json` to add another permitted official career page or RSS feed.
