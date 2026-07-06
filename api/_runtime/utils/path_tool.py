import os

def get_abs_path(path_relative_to_root: str) -> str:
    """
    Returns the absolute path relative to the project root.
    Assuming this file is located in `project_root/utils/path_tool.py`
    """
    # utils_dir = os.path.dirname(os.path.abspath(__file__))
    # project_root = os.path.dirname(utils_dir)
    # We can also use cwd if the app is always run from root, but file relative is safer.
    
    current_file = os.path.abspath(__file__)
    utils_dir = os.path.dirname(current_file)
    project_root = os.path.dirname(utils_dir)
    
    return os.path.join(project_root, path_relative_to_root)
