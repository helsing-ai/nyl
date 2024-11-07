{
  description = "Nyl is a high-level Kubernetes project management tool.";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    pyproject-nix = {
      url = "github:nix-community/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:adisbladis/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # TODO: Build argocd-cmp Docker image with Nix.

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, uv2nix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
        overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
        pyprojectOverrides = _final: _prev:
          {
            # Implement build fixups here.
          };
        pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (nixpkgs.lib.composeExtensions overlay pyprojectOverrides);

        mypyConfig = pkgs.writeText "mypy.ini" ''
          [mypy]
          explicit_package_bases = true
          namespace_packages = true
          show_column_numbers = true
          strict = true
          mypy_path = src
        '';

        ruffConfig = pkgs.writeText "ruff.toml" ''
          line-length = 120
        '';

        devEnv = pythonSet.mkVirtualEnv "dev" workspace.deps.all;
        dmypy = "${devEnv}/bin/dmypy";
        ruff = "${devEnv}/bin/ruff";
        pytest = "${devEnv}/bin/pytest";

        dependencies =
          [ pkgs.kubernetes-helm pkgs.kyverno pkgs.sops pkgs.kubectl ];
      in {
        packages.default =
          (pythonSet.mkVirtualEnv "nyl" workspace.deps.default).overrideAttrs
          (oldAttrs: {
            runtimeInputs = oldAttrs.runtimeInputs or [ ] ++ dependencies;
          });

        # TODO: Use formatter.fmt, but it complains about missing type attribute
        # TODO: Have it also fmt the nix code
        formatter = pkgs.writeShellScriptBin "fmt" ''
          set -x
          ${ruff} --config ${ruffConfig} format .
          ${pkgs.nixfmt}/bin/nixfmt .
        '';

        packages.lint = pkgs.writeShellScriptBin "lint" ''
          set -x
          checkDir="''${1:-src}"
          ${ruff} --config ${ruffConfig} check "${./.}/$checkDir"
          ${ruff} --config ${ruffConfig} format --check "${./.}/$checkDir"
          # TODO: If we don't copy the workdir to the nix store we get more Mypy errors :(
          ${dmypy} run -- --config-file ${mypyConfig} "${./.}/$checkDir"
          ${pkgs.nixfmt}/bin/nixfmt --check .
        '';

        packages.test = pkgs.writeShellScriptBin "test" "${pytest} ${./.}";

        checks.lint = pkgs.runCommand "lint" { } ''
          # TODO: Is it an issue that this runs the Mypy daemon?
          ${self.packages.${system}.lint}/bin/lint
          echo Done > $out
        '';

        checks.test = pkgs.runCommand "test" { } ''
          ${self.packages.${system}.test}/bin/test
          echo Done > $out
        '';

        devShells.default = pkgs.mkShell { buildInputs = [ devEnv ] ++ dependencies; };
      });
}
