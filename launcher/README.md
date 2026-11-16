# Class Compass launcher page

A friendly "getting ready" page for the moments when the free Render server is asleep. It is separate from the main site, because a sleeping server cannot show its own page.

How it works: teachers open this page instead of the site. It checks every few seconds whether the site is awake, then sends them straight to it.

## To use it
1. Open `index.html` and replace `REPLACE-WITH-YOUR-RENDER-ADDRESS.onrender.com` with your live site address (no trailing slash).
2. Put the four files in this folder on any free static host (for example GitHub Pages, Netlify or Cloudflare Pages). **This is a new hosting setup, so it needs your decision.**
3. Teachers can then use Share > Add to Home Screen on the launcher page itself, or bookmark it.

Nothing here connects to your database or sends any data.
