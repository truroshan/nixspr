{
  description = "Nixspr - Voice-to-text transcription tool using Gemini AI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    silero-vad = {
      url = "github:snakers4/silero-vad/v5.1.2";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, silero-vad }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];

      forAllSystems = nixpkgs.lib.genAttrs systems;

      pkgsFor = system: import nixpkgs {
        inherit system;
      };

    in
    {
      packages = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          version = builtins.readFile ./.version;

          nixspr = pkgs.python3Packages.buildPythonApplication {
            pname = "nixspr";
            inherit version;

            src = ./.;

            format = "other";
            dontBuild = true;

            nativeBuildInputs = with pkgs; [ makeWrapper ];

            propagatedBuildInputs = with pkgs; [
              python3Packages.google-genai
              python3Packages.torch
              python3Packages.torchaudio
              python3Packages.soundfile
              ffmpeg
              wtype
              wl-clipboard
              libnotify
            ];

            installPhase = ''
              mkdir -p $out/bin

              # Copy the main script and version file
              cp nixspr.py $out/bin/nixspr
              cp .version $out/bin/.version
              chmod +x $out/bin/nixspr

              # Wrap with proper Python environment and VAD model path
              wrapProgram $out/bin/nixspr \
                --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.ffmpeg pkgs.wtype pkgs.wl-clipboard pkgs.libnotify ]} \
                --set NIXSPR_VAD_MODEL_PATH "${silero-vad}"
            '';

            meta = with pkgs.lib; {
              description = "Voice-to-text transcription tool using Gemini AI";
              homepage = "https://github.com/truroshan/nixspr";
              license = licenses.mit;
              platforms = platforms.linux;
              mainProgram = "nixspr";
            };
          };
        in
        {
          default = nixspr;
          nixspr = nixspr;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.nixspr}/bin/nixspr";
        };
      });

      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            buildInputs = with pkgs; [
              python3
              python3Packages.google-genai
              python3Packages.torch
              python3Packages.torchaudio
              python3Packages.soundfile
              ffmpeg
              wtype
              wl-clipboard
              libnotify
            ];

            shellHook = ''
              export NIXSPR_VAD_MODEL_PATH="${silero-vad}"

              echo "nixspr development environment"
              echo "Usage: python3 nixspr.py start|process|cancel"
              echo ""
              echo "Make sure to set NIXSPR_GEMINI_API_KEY environment variable"
              echo "Optional: NIXSPR_GEMINI_MODEL (default: gemini-2.5-flash)"
            '';
          };
        }
      );
    };
}
