python_requirements(
    name="pyproject",
    source="pyproject.toml",
)

pex_binary(
    name="reflex",
    entry_point="reflex",
    dependencies=[":pyproject"]
)

python_sources(
    name="root",
)

pex_binary(
    name="orbital-relay",
    entry_point="proxy:main",
    dependencies=[":pyproject"],
    interpreter_constraints=[">=3.13"]
)
