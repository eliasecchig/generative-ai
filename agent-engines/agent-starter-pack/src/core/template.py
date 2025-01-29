import os
import yaml
import shutil
import pathlib
import logging
import tempfile
from cookiecutter.main import cookiecutter

OVERWRITE_FOLDERS = ["app", "frontend"]
TEMPLATE_CONFIG_FILE = ".templateconfig"
DEPLOYMENT_FOLDERS = ["cloud_run", "agent_engine"]  # Add this new constant

def load_template_config(template_dir: pathlib.Path) -> dict:
    """Read .templateconfig file to get pattern configuration."""
    config_file = template_dir / TEMPLATE_CONFIG_FILE
    if not config_file.exists():
        return None
    
    with open(config_file) as f:
        return yaml.safe_load(f)


def discover_patterns() -> dict:
    """Discover all available patterns by looking for .templateconfig files."""
    patterns = {}
    patterns_dir = pathlib.Path(__file__).parent.parent.parent / "patterns"
    
    for pattern_dir in patterns_dir.iterdir():
        if pattern_dir.is_dir():
            template_dir = pattern_dir / "template"
            if template_dir.exists():
                config = load_template_config(template_dir)
                if config:
                    patterns[pattern_dir.name] = config
    
    return patterns

def copy_with_exclusions(src, dst):
    """Copy files with special handling for notebooks."""
    def should_skip(path):
        return path.suffix in ['.ipynb', '.pyc'] or '__pycache__' in str(path)
    
    if src.is_dir():
        if not dst.exists():
            dst.mkdir(parents=True)
        for item in src.iterdir():
            d = dst / item.name
            if should_skip(item):
                logging.debug(f"Skipping file: {item}")
                continue
            if item.is_dir():
                copy_with_exclusions(item, d)
            else:
                shutil.copy2(item, d)
    else:
        if not should_skip(src):
            shutil.copy2(src, dst)

def copy_with_overwrite(src_dir, dst_dir):
    """Copy directory contents with overwrite permission."""
    logging.debug(f"Starting copy_with_overwrite from {src_dir} to {dst_dir}")
    if src_dir.exists():
        if not dst_dir.exists():
            dst_dir.mkdir(parents=True)
        for item in src_dir.iterdir():
            d = dst_dir / item.name
            logging.debug(f"Processing item: {item} -> {d}")
            
            if item.is_dir():
                copy_with_overwrite(item, d)
            else:
                logging.debug(f"Copying file: {item} -> {d}")
                shutil.copy2(item, d)
    else:
        logging.debug(f"Source directory does not exist: {src_dir}")

def copy_deployment_files(deployment_target: str, pattern_path: pathlib.Path, project_template: pathlib.Path):
    """Copy files from the specified deployment target folder."""
    if not deployment_target:
        return
        
    # Change this to look in the global deployment_targets directory
    deployment_path = (pathlib.Path(__file__).parent.parent / 
                      "deployment_targets" / deployment_target)
    
    if deployment_path.exists():
        logging.debug(f"Copying deployment files from {deployment_path}")
        # Copy all files from deployment target folder to project root
        copy_with_overwrite(deployment_path, project_template)
    else:
        logging.warning(f"Deployment target directory not found: {deployment_path}")

def apply_template_overrides(overrides_path: pathlib.Path, project_template: pathlib.Path):
    """
    Apply template overrides from the special overrides folder.
    Files in the overrides folder should maintain the full path structure 
    relative to the project root.
    """
    if not overrides_path.exists():
        return

    for item in overrides_path.rglob("*"):
        if item.is_file():
            # Get the relative path from the overrides folder
            rel_path = item.relative_to(overrides_path)
            # Construct destination path
            dest_path = project_template / rel_path
            # Ensure parent directories exist
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy the file
            shutil.copy2(item, dest_path)
            logging.debug(f"Applied template override: {rel_path}")

def process_template(pattern_name: str, template_dir: str, project_name: str, deployment_target: str = None, include_pipeline: bool = False):
    """Process the template directory and create a new project."""
    logging.debug(f"Processing template from {template_dir}")
    logging.debug(f"Project name: {project_name}")
    logging.debug(f"Include pipeline: {include_pipeline}")
    
    # Get paths
    pattern_path = pathlib.Path(template_dir).parent  # Get parent of template dir
    logging.debug(f"Pattern path: {pattern_path}")
    logging.debug(f"Pattern path exists: {pattern_path.exists()}")
    logging.debug(f"Pattern path contents: {list(pattern_path.iterdir()) if pattern_path.exists() else 'N/A'}")
    
    base_template_path = pathlib.Path(__file__).parent.parent / "base_template"
    destination_dir = pathlib.Path.cwd()  # Store the original destination directory
    
    # Create a new temporary directory and use it as our working directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        os.chdir(temp_path)  # Change to temp directory at the start
        
        # Create the cookiecutter template structure
        cookiecutter_template = temp_path / "template"
        cookiecutter_template.mkdir(parents=True)
        
        # Create the project template directory
        project_template = cookiecutter_template / "{{cookiecutter.project_name}}"
        project_template.mkdir(parents=True)
        
        # Copy base template files into project template directory
        base_template_path = pathlib.Path(__file__).parent.parent / "base_template"
        copy_with_exclusions(base_template_path, project_template)
        logging.debug(f"Copied base template from {base_template_path} to {project_template}")
        
        # Copy pattern-specific files if they exist
        if pattern_path.exists():
            # Handle app and frontend folders with overwrite
            for folder in OVERWRITE_FOLDERS:
                pattern_folder = pattern_path / folder
                project_folder = project_template / folder
                if pattern_folder.exists():
                    logging.debug(f"Pattern folder contents for {folder}: {list(pattern_folder.iterdir())}")
                    copy_with_overwrite(pattern_folder, project_folder)
                    logging.debug(f"Project folder contents after copy for {folder}: {list(project_folder.iterdir())}")
                    logging.debug(f"Copied pattern {folder} files from {pattern_folder} to {project_folder}")
            
            # Only handle template_overrides from the template folder
            template_path = pathlib.Path(template_dir)
            template_overrides = template_path / "template_overrides"
            if template_overrides.exists():
                apply_template_overrides(template_overrides, project_template)
                logging.debug("Applied template overrides")

            # Copy pattern README.md if it exists
            pattern_readme = pattern_path / "README.md"
            if pattern_readme.exists():
                pattern_readme_dest = project_template / "PATTERN_README.md"
                shutil.copy2(pattern_readme, pattern_readme_dest)
                logging.debug(f"Copied pattern README from {pattern_readme} to {pattern_readme_dest}")

            # Load template config to get deployment target
            template_path = pathlib.Path(template_dir)
            template_config = load_template_config(template_path)
            if template_config and "settings" in template_config:
                available_targets = template_config["settings"].get("deployment_targets", [])
                if isinstance(available_targets, str):
                    available_targets = [available_targets]
                
                # Validate and process deployment target if specified
                if deployment_target:
                    if deployment_target not in available_targets:
                        raise ValueError(f"Invalid deployment target '{deployment_target}'. Available targets: {available_targets}")
                    if deployment_target in DEPLOYMENT_FOLDERS:
                        copy_deployment_files(deployment_target, pattern_path, project_template)
                        logging.debug(f"Processed deployment files for target: {deployment_target}")
        
        # Create cookiecutter.json in the template root
        cookiecutter_config = {
            "project_name": "my-project",
            "pattern_name": pattern_name,
            "_copy_without_render": ["*"]  # Skip all files by default
        }
        with open(cookiecutter_template / "cookiecutter.json", "w") as f:
            import json
            json.dump(cookiecutter_config, f, indent=4)
        
        logging.debug(f"Template structure created at {cookiecutter_template}")
        logging.debug(f"Directory contents: {list(cookiecutter_template.iterdir())}")
        

        # Process the template
        try:
            cookiecutter(
                str(cookiecutter_template),
                no_input=True,
                extra_context={
                    "project_name": project_name,
                    "pattern_name": pattern_name
                }
            )
            logging.debug("Template processing completed successfully")
            
            # Copy notebooks separately after template processing
            output_dir = temp_path / str(project_name)
            notebooks_dir = output_dir / "notebooks"
            notebooks_dir.mkdir(exist_ok=True)
            
            # Copy notebooks from base template
            base_notebooks = base_template_path / "notebooks"
            if base_notebooks.exists():
                for nb in base_notebooks.glob("*.ipynb"):
                    shutil.copy2(nb, notebooks_dir)
            
            # Copy pattern-specific notebooks if they exist
            pattern_notebooks = pattern_path / "notebooks"
            if pattern_notebooks.exists():
                for nb in pattern_notebooks.glob("*.ipynb"):
                    shutil.copy2(nb, notebooks_dir)
            
            # Move the generated project to the final destination
            final_destination = destination_dir / project_name
            logging.debug(f"Moving project from {output_dir} to {final_destination}")
            
            if output_dir.exists():
                if final_destination.exists():
                    shutil.rmtree(final_destination)
                shutil.copytree(output_dir, final_destination)
                logging.debug(f"Project successfully created at {final_destination}")
            else:
                logging.error(f"Generated project directory not found at {output_dir}")
                raise FileNotFoundError(f"Generated project directory not found at {output_dir}")
                    
        except Exception as e:
            logging.error(f"Failed to process template: {str(e)}")
            raise
