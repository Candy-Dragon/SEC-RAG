"""Evaluate a saved experiment; no answer generation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sec_rag.evaluation.four_methods import main
if __name__ == "__main__":
    main()
