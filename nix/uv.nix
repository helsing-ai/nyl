{ makeOverridable, lib, callPackage, uv2nix, pyproject-nix }: {

  # Load a UV project from a directory that contains a `uv.lock` and `pyproject.toml` file.
  # The returned attrset allows you to access virtual environments for this project, as well as the commands
  # defined in the project's `[project.scripts]` section.
  loadProject = makeOverridable ({ workspaceRoot ? throw
      "Missing workspaceRoot. Must point to the path where the uv.lock and pyproject.toml lives."
    , python ? throw "Missing python.", sourcePreference ? "wheel"
    , pyprojectOverrides ? (_final: _prev: { }), }: rec {
      workspace = uv2nix.lib.workspace.loadWorkspace { inherit workspaceRoot; };
      overlay = workspace.mkPyprojectOverlay { inherit sourcePreference; };
      pythonSet = ((callPackage pyproject-nix.build.packages {
        inherit python;
      }).overrideScope (lib.composeExtensions overlay pyprojectOverrides));

      venv = {
        # This derivation contains the virtual environment with only runtime dependencies.
        default = pythonSet.mkVirtualEnv "default-venv" workspace.deps.default;

        # This derivation contains the virtual environment also with development dependencies.
        dev = pythonSet.mkVirtualEnv "dev-venv" workspace.deps.all;
      };

      # Get the path to command in the default virtualenv.
      command = (name: "${venv.default}/bin/${name}");

      # Get the path to command in the develop virtualenv, this is commonly development dependencies such
      # as pytest, ruff, mypy, etc.
      devCommand = (name: "${venv.dev}/bin/${name}");

      # Create a derivation that invokes the given "script" from the `[project.scripts]` section of the project,
      # or any script that is installed into the virtual environment per the project's dependencies.
      script = (name:
        { runtimeInputs ? [ ] }:
        (pythonSet.mkVirtualEnv name workspace.deps.default).overrideAttrs
        (oldAttrs: {
          runtimeInputs = oldAttrs.runtimeInputs or [ ] ++ runtimeInputs;
        }));

    });
}
