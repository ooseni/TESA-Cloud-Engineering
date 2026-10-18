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
  <title>Hardened EC2 web server</title>
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
    <h1>Hardened EC2 web server</h1>
    <p class="lede">nginx on Amazon Linux 2023, built and configured by Terraform.</p>
    <ul>
      <li>no SSH key and no port 22: administrators use AWS Systems Manager Session Manager;</li>
      <li>the instance metadata service accepts IMDSv2 requests only;</li>
      <li>the disk is encrypted;</li>
      <li>the security group lets HTTP in and only HTTPS out.</li>
    </ul>
    <p>Part of <a href="https://github.com/ooseni/TESA-Cloud-Engineering">TESA-Cloud-Engineering</a>, module 12.</p>
  </main>
</body>
</html>
HTML

systemctl enable --now nginx
