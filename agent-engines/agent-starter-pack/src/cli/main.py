import os
import click
import pathlib
import logging
import subprocess
import yaml
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from src.core.template import process_template, load_template_config
from src.core.gcp import setup_gcp, verify_credentials

console = Console()

def get_available_patterns() -> dict:
    """Dynamically load available patterns from the patterns directory."""
    patterns_list = []
    patterns_dir = pathlib.Path(__file__).parent.parent.parent / "patterns"
    
    for pattern_dir in patterns_dir.iterdir():
        if pattern_dir.is_dir() and not pattern_dir.name.startswith('__'):
            template_config_path = pattern_dir / "template" / ".templateconfig"
            if template_config_path.exists():
                try:
                    with open(template_config_path, 'r') as f:
                        config = yaml.safe_load(f)
                    pattern_name = pattern_dir.name
                    description = config.get("description", "No description available")
                    patterns_list.append({
                        'name': pattern_name,
                        'description': description
                    })
                except Exception as e:
                    logging.warning(f"Could not load pattern from {pattern_dir}: {e}")
    
    # Sort patterns alphabetically by name
    patterns_list.sort(key=lambda x: x['name'])
    
    # Convert to numbered dictionary starting from 1
    patterns = {i+1: pattern for i, pattern in enumerate(patterns_list)}
    
    return patterns

def get_deployment_targets(pattern_name: str) -> list:
    """Get available deployment targets for the selected pattern."""
    template_path = pathlib.Path(__file__).parent.parent.parent / "patterns" / pattern_name / "template"
    config = load_template_config(template_path)
    
    if config and config.get("settings", {}).get("deployment_targets"):
        targets = config["settings"]["deployment_targets"]
        return targets if isinstance(targets, list) else [targets]
    return []

def prompt_deployment_target(pattern_name: str) -> str:
    """Ask user to select a deployment target for the pattern."""
    targets = get_deployment_targets(pattern_name)
    
    # Define deployment target friendly names and descriptions
    TARGET_INFO = {
        "agent_engine": {
            "display_name": "Vertex AI Agent Engine",
            "description": "Vertex AI Managed platform for scalable agent deployments"
        },
        "cloud_run": {
            "display_name": "Cloud Run", 
            "description": "GCP Serverless container execution"
        }
    }
    
    if not targets:
        return None
        
    console.print("\n> Please select a deployment target:")
    for idx, target in enumerate(targets, 1):
        info = TARGET_INFO.get(target, {})
        display_name = info.get("display_name", target)
        description = info.get("description", "")
        console.print(f"{idx}. {display_name} - {description}")
    
    choice = IntPrompt.ask(
        "\nEnter the number of your deployment target choice",
        default=1,
        show_default=True
    )
    return targets[choice - 1]

def prompt_data_pipeline(pattern_name: str) -> bool:
    """Ask user if they want to include data pipeline if the pattern supports it."""
    template_path = pathlib.Path(__file__).parent.parent.parent / "patterns" / pattern_name / "template"
    config = load_template_config(template_path)
    
    if config and config.get("settings", {}).get("supports_data_pipeline"):
        return Prompt.ask(
            "\n> This pattern supports a data pipeline. Would you like to include it?",
            choices=["y", "n"],
            default="n"
        ).lower() == "y"
    return False

def get_template_path(pattern_name: str, debug: bool = False) -> str:
    """Get the absolute path to the pattern template directory."""
    current_dir = pathlib.Path(__file__).parent.parent.parent
    template_path = current_dir / "patterns" / pattern_name / "template"
    if debug:
        logging.debug(f"Looking for template in: {template_path}")
        logging.debug(f"Template exists: {template_path.exists()}")
        if template_path.exists():
            logging.debug(f"Template contents: {list(template_path.iterdir())}")
    
    # Just verify the template directory exists
    if not template_path.exists():
        raise ValueError(f"Template directory not found at {template_path}")
    
    return str(template_path)

def display_pattern_selection():
    patterns = get_available_patterns()
    
    if not patterns:
        raise ValueError("No valid patterns found in the patterns directory")
    
    console.print("\n> Please select a pattern to get started:")
    for num, pattern in patterns.items():
        console.print(f"{num}. [bold]{pattern['name']}[/] - [dim]{pattern['description']}[/]")
    
    choice = IntPrompt.ask(
        "\nEnter the number of your template choice",
        default=1,
        show_default=True
    )
    
    if choice not in patterns:
        raise ValueError(f"Invalid pattern selection: {choice}")
        
    return patterns[choice]['name']

@click.command()
@click.argument('project_name')
@click.option('--debug', is_flag=True, help="Enable debug logging")
def cli(project_name, debug):
    """Create GCP-based AI agent projects from templates."""
    try:
        # Display welcome banner
        console.print("\n=== GCP Agent Starter v0.1 :rocket:===", style="bold blue")
        console.print(
            "Welcome to GCP Agent Starter!"
        )
        console.print("This tool will help you template/scaffold an end-to-end production-ready AI agent in GCP!\n")
        # Setup debug logging if enabled
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            console.print("> Debug mode enabled")
            logging.debug("Starting CLI in debug mode")

        # Check if directory exists first
        if pathlib.Path(project_name).exists():
            console.print(f"Error: Directory '{project_name}' already exists", style="bold red")
            return
            
        # Pattern selection
        pattern = display_pattern_selection()
        if debug:
            logging.debug(f"Selected pattern: {pattern}")
            
        # Deployment target selection
        deployment_target = prompt_deployment_target(pattern)
        if debug:
            logging.debug(f"Selected deployment target: {deployment_target}")

        # Data pipeline prompt
        include_pipeline = prompt_data_pipeline(pattern)
        if debug:
            logging.debug(f"Include data pipeline: {include_pipeline}")
        
        # GCP Setup
        with console.status("[bold blue]Setting up GCP environment...", spinner="dots"):
            if debug:
                logging.debug("Setting up GCP...")
            setup_gcp()
        
        # Verify GCP credentials
        if debug:
            logging.debug("Verifying GCP credentials...")
        creds_info = verify_credentials()
        
        change_creds = Prompt.ask(
            f"\n> You are logged in with account '{creds_info['account']}' "
            f"and using project '{creds_info['project']}'. "
            "Do you wish to change this?",
            choices=["y", "n"],
            default="n"
        ).lower() == "y"
        
        if change_creds:
            try:
                console.print("\n> Initiating new login...")
                subprocess.run(
                    ["gcloud", "auth", "login", "--update-adc"],
                    check=True
                )
                console.print("> Login successful. Verifying new credentials...")
                
                # Re-verify credentials after login
                new_creds_info = verify_credentials()
                
                # Prompt for project change
                change_project = Prompt.ask(
                    f"\n> You are now logged in with account '{new_creds_info['account']}'. "
                    f"Current project is '{new_creds_info['project']}'. "
                    "Do you wish to change the project?",
                    choices=["y", "n"],
                    default="n"
                ).lower() == "y"
                
                if change_project:
                    # Prompt for new project ID
                    new_project = Prompt.ask("\n> Enter the new project ID")
                    
                    try:
                        # Set the project in gcloud config
                        console.print(f"\n> Setting project to {new_project}...")
                        subprocess.run(
                            ["gcloud", "config", "set", "project", new_project],
                            check=True
                        )
                        
                        # Set the application default quota project
                        console.print("> Setting application default quota project...")
                        subprocess.run(
                            ["gcloud", "auth", "application-default", "set-quota-project", new_project],
                            check=True
                        )
                        
                        console.print(f"> Successfully switched to project: {new_project}")
                        
                        # Re-verify credentials one final time
                        final_creds_info = verify_credentials()
                        console.print(f"\n> Now using account '{final_creds_info['account']}' "
                                    f"with project '{final_creds_info['project']}'")
                        
                    except subprocess.CalledProcessError as e:
                        console.print("\n> Error while changing project. Please verify the project ID and try again.", 
                                    style="bold red")
                        if debug:
                            logging.debug(f"Project change error: {str(e)}")
                        return
                
            except subprocess.CalledProcessError as e:
                console.print("\n> Error during login process. Please try again.", style="bold red")
                if debug:
                    logging.debug(f"Login error: {str(e)}")
                return
            except Exception as e:
                console.print(f"\n> Unexpected error: {str(e)}", style="bold red")
                if debug:
                    logging.debug(f"Unexpected error during login: {str(e)}")
                return
        
        console.print("> Testing GCP and Vertex AI Connection...")
        # Process template
        template_path = get_template_path(pattern, debug=debug)
        if debug:
            logging.debug(f"Template path: {template_path}")
            logging.debug(f"Processing template for project: {project_name}")
        process_template(
            pattern, 
            template_path, 
            project_name, 
            deployment_target=deployment_target,
            include_pipeline=include_pipeline
        )
            
        console.print("> GCP tests were successful you are ready to Start!")
        console.print("\n> 👍 Done. Execute the following command to get started:")
        console.print(f"> cd {project_name} && make playground")
        
    except Exception as e:
        if debug:
            logging.exception("An error occurred:")  # This will print the full stack trace
        console.print(f"Error: {str(e)}", style="bold red")

if __name__ == '__main__':
    cli()
