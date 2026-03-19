python_requirements(
    name="pyproject",
    source="pyproject.toml",
)

pex_binary(
    name="reflex",
    entry_point="reflex",
    dependencies=[":pyproject"]
)

files(name="assets", sources=["assets/*"])

resource(
    name="rxconfig",
    source="rxconfig.py"
)

pex_binary(
    name="orbital-relay",
    entry_point="proxy:main",
    dependencies=[":pyproject"],
    interpreter_constraints=[">=3.13"]
)

pex_binary(
    name="orbitlab-backend",
    entry_point="reflex",
    args=["run"],
    dependencies=["orbitlab:orbitlab", ":pyproject"],
    interpreter_constraints=[">=3.13"],
    env={
        "REFLEX_BACKEND_ONLY": "True",
        "REFLEX_BACKEND_PORT": "8081",
        "REFLEX_FRONTEND_PORT": "8080",
        "REFLEX_ENV_MODE": "prod",
        "REFLEX_SKIP_COMPILE": "True",
    }
)
