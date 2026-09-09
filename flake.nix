{
  description = "Site Health Check dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgs = forAllSystems (system: nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (system: {
        default = pkgs.${system}.mkShellNoCC {
          packages = with pkgs.${system}; [
            # Python / Backend
            poetry
            python311
            pyright
            ruff

            # Nix
            nil

            # Frontend Runtime & Package Managers
            nodejs_22
            bun

            # Language Servers (LSP) for Helix / Editor
            typescript
            typescript-language-server
            tailwindcss-language-server
            vscode-langservers-extracted
          ];
        };
      });
    };
}

