shell_sources()
python_source(name="web-server", source="static_webserver.py")

pex_binary(
    name="orbitlab-frontend",
    entry_point="scripts.static_webserver:main",
    dependencies=[":web-server"],
    interpreter_constraints=[">=3.13"]
)

adhoc_tool(
    name="static-html",
    runnable="//:reflex",
    args=["export", "--frontend-only"],
    execution_dependencies=["//:rxconfig", "orbitlab:orbitlab", "//:assets"],
    output_files=["frontend.zip"],
    log_output=True,
    workdir="/",
)

run_shell_command(
    name="build",
    command="bash build-deb.sh",
    execution_dependencies=[
        "resources:resources",
        ":static-html",
        "//:orbitlab-backend",
        ":orbitlab-frontend",
        "//:rxconfig",
    ],
)
