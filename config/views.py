from django.conf import settings
from django.http import HttpResponse

FALLBACK = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AICTE FDR Portal</title></head>
<body style="font-family:system-ui,sans-serif;max-width:640px;margin:4rem auto;padding:0 1rem">
<h1>The web interface has not been built yet</h1>
<p>Run <code>npm install</code> and <code>npm run build</code> in the <code>frontend</code> folder,
or run <code>bash build.sh</code> from the project root. The API is still available at <code>/api/</code>.</p>
</body></html>"""


def spa_index(request, *args, **kwargs):
    """Serve the built React app's entry page for every front-end route (e.g. /fdrs, /verification)."""
    index = settings.BASE_DIR / "frontend" / "dist" / "index.html"
    if not index.exists():
        return HttpResponse(FALLBACK, status=503, content_type="text/html")
    return HttpResponse(index.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")
