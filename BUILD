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
