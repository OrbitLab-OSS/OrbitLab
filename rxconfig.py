"""Reflex Config."""

import os

import reflex as rx
from vite_config_plugin import ViteConfigPlugin


config = rx.Config(
    app_name="orbitlab",
    app_module_import="orbitlab.web",
    redis_url=os.environ.get("ORBITLAB_REDIS_URL", "redis://127.0.0.1:6379/11"), # Set to a non-default DB
    redis_lock_warning_threshold=2500,
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.RadixThemesPlugin(),
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
        ViteConfigPlugin({
            "optimizeDeps": {"include": ["react-sortablejs", "@xterm/xterm"]},
            "ssr": {"noExternal": ["react-sortablejs", "@xterm/xterm"]},
        }),
    ],
)
