import argparse

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080, help="Port number")
    args = parser.parse_args()
    
    routes = [
        Mount('/', app=StaticFiles(directory='/opt/orbitlab/web', html=True), name="orbitlab"),
    ]

    app = Starlette(routes=routes)
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
