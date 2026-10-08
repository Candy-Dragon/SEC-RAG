"""Run the current four-method evaluator; source/output directories are configurable."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from sec_rag.evaluation.four_methods import main
if __name__ == "__main__":
    main()
