"""Download xx_ent_wiki_sm for NER-based structural detection (Sprint 2 P4).

Run once after `pip install -r requirements.txt`:
    python scripts/install_spacy_model.py

Equivalent to: python -m spacy download xx_ent_wiki_sm
"""

import subprocess
import sys


def main() -> None:
    print("Downloading spaCy model: xx_ent_wiki_sm (~12 MB)...")
    result = subprocess.run(
        [sys.executable, "-m", "spacy", "download", "xx_ent_wiki_sm"],
        check=False,
    )
    if result.returncode == 0:
        print("Done. xx_ent_wiki_sm installed.")
    else:
        print(
            "Download failed (exit code %d). Try manually:\n"
            "    python -m spacy download xx_ent_wiki_sm" % result.returncode,
            file=sys.stderr,
        )
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
