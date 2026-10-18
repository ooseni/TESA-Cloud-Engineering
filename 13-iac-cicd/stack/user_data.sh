#!/bin/bash
# EC2 user data: runs once, as root, at first boot. Output: /var/log/cloud-init-output.log
set -euo pipefail

dnf install -y nginx

cat > /usr/share/nginx/html/index.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Deployed by the pipeline</title>
  <style>
    :root { color-scheme: light dark; --fg: #1a1a1a; --bg: #ffffff; --muted: #555555; --accent: #0b5cad; }
    @media (prefers-color-scheme: dark) { :root { --fg: #f0f0f0; --bg: #111111; --muted: #b0b0b0; --accent: #7fb6ff; } }
    body { margin: 0; background: var(--bg); color: var(--fg); font: 18px/1.6 system-ui, sans-serif; }
    main { max-width: 40rem; margin: 0 auto; padding: 3rem 1.25rem; }
    h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 0.5rem; }
    p.lede { color: var(--muted); margin-top: 0; }
    a { color: var(--accent); }
  </style>
</head>
<body>
  <main>
    <h1>Deployed by the pipeline</h1>
    <p class="lede">Planned on a pull request, applied by hand from main, with short-lived AWS credentials.</p>
    <ul>
      <li>GitHub Actions signed in to AWS with OpenID Connect: no stored access keys;</li>
      <li>the plan was posted to the pull request with a checksum, and only that plan could be applied;</li>
      <li>the state lives in S3, versioned and locked.</li>
    </ul>
    <p>Part of <a href="https://github.com/ooseni/TESA-Cloud-Engineering">TESA-Cloud-Engineering</a>, module 13.</p>
  </main>
</body>
</html>
HTML

systemctl enable --now nginx
