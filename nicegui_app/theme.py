"""One dark theme, applied everywhere via page_shell (goal #3 + #5).

Matches the existing tool's look: near-black blue background, purple accent,
Syne for headings + IBM Plex Mono for data. Called once at the top of every
page so the whole app reads as one system.
"""

from __future__ import annotations

from nicegui import ui

PRIMARY = "#7c5cff"      # purple accent
BG = "#0d0d15"           # near-black with a blue tint
SURFACE = "#12121f"      # cards
BORDER = "#23233a"
TEXT = "#e8e8f0"
MUTED = "#9b9bb8"

_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root { --seo-primary: #7c5cff; }
  body, .q-page, .nicegui-content, .q-btn, .q-field, input, textarea, .q-item {
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
  }
  body, .q-page, .nicegui-content { background: #0d0d15 !important; color: #e8e8f0; }
  h1,h2,h3,h4, .text-2xl, .text-lg, .font-bold, .font-semibold {
      font-family: 'Syne', 'Inter', sans-serif !important; letter-spacing: -0.01em;
  }
  code, .font-mono { font-family: 'IBM Plex Mono', monospace; }
  /* NEVER override the icon ligature font — keep Material Icons on glyphs */
  .q-icon, i.material-icons, .material-icons, .notranslate {
      font-family: 'Material Icons' !important;
  }
  /* cards */
  .q-card { background: #12121f !important; border: 1px solid #23233a !important;
            box-shadow: none !important; border-radius: 10px !important; }
  /* left drawer + header */
  .q-drawer { background: #0a0a12 !important; border-right: 1px solid #23233a !important; }
  .q-header { background: linear-gradient(90deg,#12121f,#0d0d15) !important;
              border-bottom: 1px solid #23233a; }
  /* tables read as data */
  .q-table thead th { color: #9b9bb8 !important; font-size: 0.72rem;
                      text-transform: uppercase; letter-spacing: 0.06em; }
  .q-table tbody td { color: #d6d6ea !important; }
  .text-gray-500, .text-gray-600 { color: #9b9bb8 !important; }
  /* subtle scrollbar */
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-thumb { background: #23233a; border-radius: 6px; }
</style>
"""

_applied_key = "_theme_head_applied"


def apply() -> None:
    """Enable dark mode + brand colors + fonts/CSS for the current page."""
    ui.dark_mode().enable()
    ui.colors(
        primary=PRIMARY, secondary="#5533ff", accent="#33dd88",
        dark=BG, dark_page=BG,
        positive="#33dd88", negative="#ff4455", warning="#ffaa33", info="#5bb4d4",
    )
    ui.add_head_html(_HEAD)
