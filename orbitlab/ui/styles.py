"""OrbitLab visual tokens shared by NiceGUI components."""

from nicegui import ui


class OrbitLabTheme:
    """Defines the existing OrbitLab visual language in one location."""

    ACCENT = "#36E2F4"
    PRIMARY = "#1E63E9"
    VIOLET = "#994BF1"
    TEXT = "#E8F1FF"
    MUTED = "#AEB9CC"
    SURFACE = "#0E1015"
    SURFACE_RAISED = "#14171D"

    @classmethod
    def install(cls) -> None:
        """Install the palette and CSS before the first page is rendered."""
        ui.colors(primary=cls.PRIMARY, secondary=cls.ACCENT, accent=cls.VIOLET, dark=cls.SURFACE)
        ui.add_head_html(
            """
            <style>
              :root { color-scheme: dark; }
              body {
                background: linear-gradient(180deg, #111317 0%, #151820 100%);
                color: #E8F1FF;
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
                  "Segoe UI", sans-serif;
              }
              .ol-page { min-height: 100vh; background: linear-gradient(180deg, #111317, #151820); }
              .ol-sidebar { background: rgba(14, 16, 21, .90); border-right: 1px solid rgba(255,255,255,.08); }
              .ol-card { background: linear-gradient(180deg, rgba(14,16,21,.88), rgba(18,20,26,.94));
                border: 1px solid rgba(255,255,255,.10); box-shadow: 0 4px 18px rgba(0,0,0,.24); }
              .ol-card:hover { border-color: rgba(54,226,244,.40); }
              .ol-muted { color: #AEB9CC; }
              .ol-table .q-table__top, .ol-table thead tr { background: rgba(255,255,255,.03); }
              .ol-table tbody tr:hover { background: rgba(255,255,255,.06); }
              .ol-nav-active { background: rgba(14,116,144,.35); color: #7DECF8; }
            </style>
            """
        )
