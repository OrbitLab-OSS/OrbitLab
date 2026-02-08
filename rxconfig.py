"""Reflex Config."""

import reflex as rx

config = rx.Config(
    app_name="orbitlab",
    app_module_import="orbitlab.web.main",
    redis_url="redis://192.168.87.230:6379",
    plugins=[
        rx.plugins.TailwindV4Plugin(
            {
                "darkMode": "class",
                "theme": {
                    "screens": {
                        "sm": "500px",
                        "md": "900px",
                        "lg": "1300px",
                        "xl": "2000px",
                    },
                },
            },
        ),
        rx.plugins.sitemap.SitemapPlugin(),
    ],
)
