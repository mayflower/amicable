"""Fix dev-server/HMR config for reverse-proxied previews (avoid ws://:::3000)."""
from __future__ import annotations

import re
from pathlib import Path

p = Path("/app/vite.config.ts")
text = p.read_text(encoding="utf-8")

# Replace a problematic IPv6/hardcoded HMR host config from the upstream template.
text2 = re.sub(
    r"server:\s*\{[\s\S]*?\}\s*\n\s*\}\s*\);\s*$",
    (
        "server: {\n"
        '    host: "0.0.0.0",\n'
        "    port: 3000,\n"
        "    strictPort: true,\n"
        "    hmr: {\n"
        '      protocol: "wss",\n'
        "      clientPort: 443,\n"
        "    },\n"
        "  }\n"
        "});\n"
    ),
    text,
    count=1,
)

# Fallback: if the expected shape changed, do a smaller targeted rewrite.
if text2 == text:
    text2 = text.replace('host: "::"', 'host: "0.0.0.0"').replace(
        'protocol: "ws"', 'protocol: "wss"'
    )

p.write_text(text2, encoding="utf-8")
