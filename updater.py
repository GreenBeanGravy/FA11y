import os
import sys
import subprocess
import time
import concurrent.futures
from functools import lru_cache
from typing import Optional
import configparser

def print_info(message):
    """Prints information to the console."""
    print(message)

def ensure_required_modules():
    """Check and install required modules."""
    required_modules = ['requests', 'psutil', 'argparse']
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            print_info(f"Installing required module: {module}")
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                         check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
    # Now you can safely import your modules
    global requests, argparse
    import requests
    import argparse

# Run module check before anything else
ensure_required_modules()

# Set the command window title
os.system("title FA11y")

# Suppress Pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# Configuration
AUTO_UPDATE_UPDATER = True
MAX_RESTARTS = 3

def read_config_boolean(config_path='config.txt', section='Toggles', key='BetaUpdates'):
    """Read boolean value from config file."""
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        value = config.get(section, key).split('"')[0].strip().lower()
        return value == 'true'
    except:
        return False  # Default to main branch if config reading fails

def get_target_branch():
    """Get the target branch based on config setting."""
    use_beta = read_config_boolean()
    return 'beta' if use_beta else 'main'

def install_required_modules():
    """
    Install required Python modules using pip and handle any import errors.
    """
    modules = ['requests', 'psutil']
    
    # Check for pywin32
    try:
        import win32api
    except ImportError:
        modules.append('pywin32')
    
    # Install all required modules concurrently
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(lambda module: subprocess.run(
            [sys.executable, '-m', 'pip', 'install', module],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ), modules)

def install_accessible_output2():
    """
    Installs the accessible_output2 module from a wheel or PyPI.
    """
    module = 'accessible_output2'
    wheel_path = os.path.join(os.getcwd(), 'whls', 'accessible_output2-0.17-py2.py3-none-any.whl')
    try:
        print_info(f"Installing {module} from wheel")
        subprocess.run([sys.executable, '-m', 'pip', 'install', wheel_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        try:
            print_info(f"Installing {module} from PyPI")
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print_info(f"Failed to install {module}")
            return False
    return True

def download_file_to_path(url, path):
    """
    Downloads a file from a URL to a specified local path.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(path, 'wb') as f:
            f.write(response.content)
    except requests.RequestException as e:
        print_info(f"Failed to download {url}: {e}")

def download_folder(repo, branch, folder):
    """
    Downloads all files in a GitHub repository folder to a local folder.
    """
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        files = response.json()
        os.makedirs(folder, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(download_file_to_path, file['download_url'], os.path.join(folder, file['name'])) 
                      for file in files if file['type'] == 'file']
            concurrent.futures.wait(futures)
        print_info(f"Downloaded folder: {folder}")
    except requests.RequestException as e:
        print_info(f"Failed to download folder {folder}: {e}")
        sys.exit(1)

def install_required_modules_and_whls():
    """
    Installs required modules and wheel files.
    """
    restart_count = int(os.environ.get('UPDATER_RESTART_COUNT', 0))
    if restart_count >= MAX_RESTARTS:
        print_info(f"Maximum restarts ({MAX_RESTARTS}) reached. Continuing without further restarts.")
        return

    install_required_modules()
    print_info("Modules installed.")

    if not os.path.exists('whls'):
        target_branch = get_target_branch()
        download_folder("GreenBeanGravy/FA11y", target_branch, "whls")

@lru_cache(maxsize=None)
def get_repo_files(repo: str, branch: str = 'main') -> list:
    """Gets the list of files in a GitHub repository branch."""
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tree = response.json().get('tree', [])
        return [item['path'] for item in tree if item['type'] == 'blob']
    except requests.RequestException as e:
        print_info(f"Failed to get repo files from {branch} branch: {e}")
        return None

def download_file(repo: str, file_path: str, branch: str = 'main') -> Optional[bytes]:
    """Downloads a single file from a GitHub repository."""
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        print_info(f"Failed to download file {file_path} from {branch} branch: {e}")
        return None

def file_needs_update(local_path, github_content):
    """
    Checks if a local file needs to be updated with new content.
    """
    if not os.path.exists(local_path):
        return True
    with open(local_path, 'rb') as file:
        return file.read() != github_content

def update_script(repo, script_name):
    """
    Updates the script from a GitHub repository if needed.
    """
    if not AUTO_UPDATE_UPDATER:
        return False
    
    target_branch = get_target_branch()
    github_content = download_file(repo, script_name, target_branch)
    
    if github_content is None or not file_needs_update(script_name, github_content):
        return False

    with open(script_name, 'wb') as file:
        file.write(github_content)
    print_info(f"Updated script: {script_name}")
    return True

def check_and_update_file(repo, file_path):
    """
    Checks if a file needs to be updated based on the target branch.
    """
    target_branch = get_target_branch()

    if file_path.lower() == 'readme.md':
        readme_content = download_file(repo, file_path, target_branch)
        if readme_content and file_needs_update('README.txt', readme_content):
            with open('README.txt', 'wb') as file:
                file.write(readme_content)
            print_info("Updated README.txt")
            return True
        return False

    if not file_path.endswith(('.py', '.txt', '.png', '.bat', '.ogg', '.jpg', '.pkl')) and file_path not in ('VERSION', 'BETA_VERSION'):
        return False

    github_content = download_file(repo, file_path, target_branch)
    if github_content is None or not file_needs_update(file_path, github_content):
        return False

    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    
    with open(file_path, 'wb') as file:
        file.write(github_content)
    print_info(f"Updated file: {file_path}")
    return True

def update_folder(repo, folder):
    """
    Updates a folder from a GitHub repository.
    """
    target_branch = get_target_branch()
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={target_branch}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        remote_files = {file['name'] for file in response.json() if file['type'] == 'file'}
        
        if os.path.exists(folder):
            local_files = set(os.listdir(folder))
            files_to_remove = local_files - remote_files
            
            for file in files_to_remove:
                os.remove(os.path.join(folder, file))
                print_info(f"Removed file from {folder} folder: {file}")
            
            return bool(files_to_remove)
        return False
    except requests.RequestException as e:
        print_info(f"Failed to update {folder} folder: {e}")
        return False

def check_legendary():
    """
    Checks if Legendary is installed or downloads it.
    """
    legendary_path = os.path.join(os.getcwd(), "legendary.exe")
    if os.path.exists(legendary_path):
        print_info("Legendary found.")
        return True

    print_info("Legendary not found. Downloading...")
    legendary_url = "https://github.com/derrod/legendary/releases/download/0.20.34/legendary.exe"
    
    try:
        download_file_to_path(legendary_url, legendary_path)
        print_info("Legendary downloaded successfully.")
        return True
    except Exception as e:
        print_info(f"Failed to download Legendary: {e}")
        return False

def install_requirements():
    """
    Install dependencies listed in requirements.txt.
    """
    requirements_file = 'requirements.txt'
    target_branch = get_target_branch()

    if not os.path.exists(requirements_file):
        print_info(f"{requirements_file} not found. Downloading from GitHub...")
        url = f"https://raw.githubusercontent.com/GreenBeanGravy/FA11y/{target_branch}/requirements.txt"
        download_file_to_path(url, requirements_file)

    print_info(f"Installing dependencies from {requirements_file}...")
    try:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', requirements_file], 
            check=True, capture_output=True, text=True
        )
        print_info("Dependencies installed successfully from requirements.txt.")
        return True
    except subprocess.CalledProcessError as e:
        print_info(f"Failed to install dependencies from {requirements_file}: {e}")
        return False

def check_version():
    """
    Checks if updates are needed based on config and file contents.
    """
    repo = "GreenBeanGravy/FA11y"
    target_branch = get_target_branch()
    
    # Check VERSION/BETA_VERSION file first
    version_file = "BETA_VERSION" if target_branch == 'beta' else "VERSION"
    if not os.path.exists(version_file):
        print_info(f"Version file not found, update needed")
        return True
        
    github_content = download_file(repo, version_file, target_branch)
    if github_content is None:
        print_info(f"Could not fetch version file from {target_branch} branch")
        return False
        
    return file_needs_update(version_file, github_content)

def main():
    """
    Main function to run the updater script.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-by-fa11y', action='store_true', help='Indicates if updater was run by FA11y')
    args = parser.parse_args()

    target_branch = get_target_branch()
    script_name = os.path.basename(__file__)

    print_info(f"Using {target_branch} branch based on configuration...")

    # Check for updater script updates first
    if update_script("GreenBeanGravy/FA11y", script_name):
        print_info("Please restart the updater for updates. Closing in 5 seconds...")
        time.sleep(5)
        sys.exit(0)

    install_required_modules_and_whls()
    
    ao2_available = install_accessible_output2()
    speaker = None

    if ao2_available:
        try:
            from accessible_output2.outputs.auto import Auto
            speaker = Auto()
        except ImportError:
            print_info("Failed to import accessible_output2. Speech output will be unavailable.")

    print_info(f"Checking and installing requirements from {target_branch} branch...")
    requirements_installed = install_requirements()

    if requirements_installed:
        print_info("All requirements installed!")
        if speaker:
            speaker.speak("All requirements installed!")
    else:
        print_info("Some updates may have failed. Please check the console output.")
        if speaker:
            speaker.speak("Some updates may have failed. Please check the console output.")

    # Check if we need to update
    update_needed = check_version()

    if update_needed:
        repo_files = get_repo_files("GreenBeanGravy/FA11y", target_branch)
        
        if repo_files:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                update_results = list(executor.map(
                    lambda file_path: check_and_update_file("GreenBeanGravy/FA11y", file_path),
                    repo_files
                ))
                updates_available = any(update_results)

            icons_updated = update_folder("GreenBeanGravy/FA11y", "icons")
            images_updated = update_folder("GreenBeanGravy/FA11y", "images")
            fa11y_updates = updates_available or icons_updated or images_updated

            if fa11y_updates:
                print_info(f"Updates processed from {target_branch} branch.")

            if not check_legendary():
                print_info("Failed to download or find Legendary. Please download it manually and add it to your system PATH.")

            print_info("Update process completed")

            if fa11y_updates:
                update_type = "beta " if target_branch == "beta" else ""
                closing_message = f"FA11y {update_type}update complete! Closing in 5 seconds..."
                if speaker:
                    speaker.speak(closing_message)
                print_info(closing_message)
                time.sleep(5)
                sys.exit(1)  # Exit with code 1 to indicate updates were installed
        else:
            print_info(f"Failed to get repository files from {target_branch} branch.")
    else:
        print_info(f"You are on the latest version of FA11y ({target_branch} branch)!")
        if speaker:
            speaker.speak(f"You are on the latest version of FA11y {target_branch} branch!")

    print_info("Closing in 5 seconds...")
    time.sleep(5)
    sys.exit(0)  # Exit with code 0 to indicate no updates were needed

if __name__ == "__main__":
    main()
