python_requirements(
    name="pyproject",
    source="pyproject.toml",
)

pex_binary(
    name="reflex",
    entry_point="reflex",
    dependencies=[":pyproject"],
)

files(name="assets", sources=["assets/*"])

resource(
    name="rxconfig",
    source="rxconfig.py"
)

pex_binary(
    name="orbitlab-backend",
    entry_point="reflex",
    args=["run"],
    dependencies=["orbitlab:orbitlab", ":pyproject"],
    interpreter_constraints=[">=3.13"],
    env={
        "REFLEX_BACKEND_ONLY": "True",
        "REFLEX_BACKEND_PORT": "8000",
        "REFLEX_ENV_MODE": "prod",
        "REFLEX_SKIP_COMPILE": "True",
    }
)

adhoc_tool(
    name="static-html",
    runnable=":reflex",
    args=["export", "--frontend-only"],
    execution_dependencies=[":rxconfig", "orbitlab:orbitlab", ":assets"],
    output_files=["frontend.zip"],
    log_output=True,
)

pex_binary(
    name="orbitlab-frontend",
    entry_point="scripts.static_webserver:main",
    dependencies=["scripts:web-server"],
    interpreter_constraints=[">=3.13"],
)

package_shell_command(
    name="orbitlab",
    command="ls -latr",
    tools=["ls"],
    execution_dependencies=[
        "resources:resources",
        "scripts:scripts",
        ":static-html",
        ":orbitlab-backend",
        ":orbitlab-frontend",
        ":rxconfig",
    ],
    output_files=["orbitlab.deb"],
)
