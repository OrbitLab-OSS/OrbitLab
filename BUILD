python_requirements(
    name="pyproject",
    source="pyproject.toml",
)

pex_binary(
    name="orbitlab-backend",
    entry_point="orbitlab.ui.main:main",
    dependencies=["orbitlab:orbitlab", ":pyproject"],
    interpreter_constraints=[">=3.13"],
)

package_shell_command(
    name="orbitlab",
    command="ls -latr",
    tools=["ls"],
    execution_dependencies=[
        "resources:resources",
        "scripts:scripts",
        ":orbitlab-backend",
    ],
    output_files=["orbitlab.deb"],
)
