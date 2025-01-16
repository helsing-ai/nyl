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
        uv = pkgs.callPackage ./nix/uv.nix { inherit uv2nix pyproject-nix; };

        uvProject = uv.loadProject {
          workspaceRoot = ./.;
          python = pkgs.python312;
          # TODO: Pass runtimeInputs here?
        };

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

        dependencies =
          [ pkgs.kubernetes-helm pkgs.kyverno pkgs.sops pkgs.kubectl ];
      in rec {
        packages.default =
          uvProject.script "nyl" { runtimeInputs = dependencies; };

        packages.docs = let
          docs = uv.loadProject {
            workspaceRoot = ./docs;
            python = pkgs.python312;
          };
          mkdocs = docs.command "mkdocs";
        in pkgs.writeShellScriptBin "docs" ''
          set -eu
          cd docs
          ${mkdocs} $@
        '';

        # TODO: Use formatter.fmt, but it complains about missing type attribute
        # TODO: Have it also fmt the nix code
        formatter = pkgs.writeShellScriptBin "fmt" ''
          set -x
          ${uvProject.devCommand "ruff"} --config ${ruffConfig} format .
          ${pkgs.nixfmt-classic}/bin/nixfmt .
        '';

        # TODO: Do not require ruff/mypy to be dependencies of the project?

        packages.lint = pkgs.writeShellScriptBin "lint" ''
          set -x
          checkDir="''${1:-src}"
          ${uvProject.devCommand "ruff"} --config ${ruffConfig} check "${
            ./.
          }/$checkDir"
          ${
            uvProject.devCommand "ruff"
          } --config ${ruffConfig} format --check "${./.}/$checkDir"
          # TODO: If we don't copy the workdir to the nix store we get more Mypy errors :(
          ${uvProject.devCommand "dmypy"} run -- --config-file ${mypyConfig} "${
            ./.
          }/$checkDir"
          ${pkgs.nixfmt-classic}/bin/nixfmt --check .
        '';

        packages.test = let
          dependenciesPath = nixpkgs.lib.concatStringsSep ":"
            (map (dep: "${dep}/bin") dependencies);
        in pkgs.writeShellScriptBin "test"
        "PATH=\${PATH}:${dependenciesPath} ${uvProject.devCommand "pytest"} ${
          ./.
        }";

        checks.lint = pkgs.runCommand "lint" { } ''
          # TODO: Is it an issue that this runs the Mypy daemon?
          ${packages.lint}/bin/lint
          echo Done > $out
        '';

        checks.test = pkgs.runCommand "test" { } ''
          ${packages.test}/bin/test
          echo Done > $out
        '';

        devShells.default =
          pkgs.mkShell { buildInputs = [ uvProject.venv.dev ] ++ dependencies; };
      });
}
