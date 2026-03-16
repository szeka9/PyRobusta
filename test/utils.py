import sys
import importlib.util
from pathlib import Path


def load_module(relative_path):
    here = Path(__file__).resolve()
    src_root = here.parent.parent / "src"

    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
        
    full_path = (src_root / relative_path).resolve()
    rel = full_path.relative_to(src_root)
    module_name = ".".join(rel.with_suffix("").parts)
    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod