import os
import sys
import subprocess
import time
import concurrent.futures
from functools import lru_cache
import winreg
import warnings
import argparse

# Suppress pkg_resources deprecation warnings from external libraries
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning)

# Check Python version requirement
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required.")
    input("Press Enter to exit...")
    sys.exit(1)

# Ensure the "requests" library is installed before importing it
try:
    import requests
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import requests

# Set the command window title
os.system("title FA11y")

# Suppress Pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# Configuration
AUTO_UPDATE_UPDATER = False
MAX_RESTARTS = 3
MONARCH_MODE = False  # When enabled, retries failed downloads indefinitely

# GitHub repository configuration
GITHUB_REPO = "GreenBeanGravy/FA11y"
GITHUB_BRANCH = "main"

# Files to ignore during updates (will not be replaced)
IGNORED_FILES = [
    'config.txt',
    'CUSTOM_POI.txt',
    'FAVORITE_POIS.txt',
]

# FakerInput configuration
FAKERINPUT_MSI_URL = "https://github.com/Ryochan7/FakerInput/releases/download/v0.1.0/FakerInput_0.1.0_x64.msi"
FAKERINPUT_MSI_FILENAME = "FakerInput_0.1.0_x64.msi"

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="FA11y Updater")
    parser.add_argument('--monarch', action='store_true', help='Enable Monarch Mode for persistent download retries')
    return parser.parse_args()

def print_info(message):
    """Prints information to the console."""
    print(message)

def check_fakerinput_installed():
    """
    Checks if FakerInput is installed on the system.
    Returns True if installed, False otherwise.
    """
    try:
        # Check registry for installed programs
        registry_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        
        for registry_path in registry_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, registry_path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    if "FakerInput" in display_name:
                                        print_info("FakerInput found in registry.")
                                        return True
                                except FileNotFoundError:
                                    continue
                        except OSError:
                            continue
            except FileNotFoundError:
                continue
        
        # Alternative check: look for executable in common locations
        common_paths = [
            r"C:\Program Files\FakerInput\FakerInput.exe",
            r"C:\Program Files (x86)\FakerInput\FakerInput.exe",
            os.path.expanduser(r"~\AppData\Local\FakerInput\FakerInput.exe")
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                print_info(f"FakerInput found at: {path}")
                return True
        
        return False
        
    except Exception as e:
        print_info(f"Error checking FakerInput installation: {e}")
        return False

def install_fakerinput():
    """
    Downloads and installs FakerInput using the MSI package.
    Returns True if successful, False otherwise.
    """
    try:
        print_info("FakerInput not found. Downloading and installing...")
        
        # Download the MSI file
        print_info("Downloading FakerInput MSI...")
        response = requests.get(FAKERINPUT_MSI_URL, stream=True)
        response.raise_for_status()
        
        # Save MSI to temporary location
        msi_path = os.path.join(os.getcwd(), FAKERINPUT_MSI_FILENAME)
        with open(msi_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print_info("Download complete. Installing FakerInput...")
        print_info("Please accept the UAC prompt and follow the installation wizard...")
        
        # Execute the MSI package with UAC
        result = subprocess.run([msi_path], shell=True)
        
        # Clean up the downloaded MSI file
        try:
            os.remove(msi_path)
        except OSError:
            pass
        
        # Check if installation was successful
        print_info("Checking if FakerInput was installed successfully...")
        if check_fakerinput_installed():
            print_info("FakerInput installed successfully.")
            return True
        else:
            print_info("FakerInput installation may have failed or was cancelled.")
            return False
            
    except requests.RequestException as e:
        print_info(f"Failed to download FakerInput: {e}")
        return False
    except Exception as e:
        print_info(f"Error installing FakerInput: {e}")
        return False

def check_and_install_fakerinput():
    """
    Checks if FakerInput is installed and installs it if not found.
    """
    if check_fakerinput_installed():
        print_info("FakerInput is already installed.")
        return True
    else:
        return install_fakerinput()

def install_required_modules():
    """
    Install required Python modules using pip only if they're not already installed.
    """
    def is_module_installed(module):
        try:
            __import__(module)
            return True
        except ImportError:
            return False

    # List of required modules
    modules = []
    
    # Check for requests
    if not is_module_installed('requests'):
        modules.append('requests')

    if not is_module_installed('packaging'):
        modules.append('packaging')
    
    # Check for psutil
    if not is_module_installed('psutil'):
        modules.append('psutil')
    
    # Check for pywin32
    try:
        import win32api
    except ImportError:
        modules.append('pywin32')
    
    if not modules:
        print_info("All required modules are already installed.")
        return
    
    # Install only missing modules
    print_info(f"Installing missing modules: {', '.join(modules)}")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(
            lambda module: subprocess.run(
                [sys.executable, '-m', 'pip', 'install', module],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ), 
            modules
        )
    
    print_info("Modules installed.")

def install_accessible_output2():
    """
    Installs the accessible_output2 module from a wheel or PyPI only if it's not already installed.
    """
    module = 'accessible_output2'
    
    # First check if the module is already installed
    try:
        import accessible_output2
        print_info(f"{module} is already installed")
        return True
    except ImportError:
        pass
    
    # If not installed, proceed with installation
    wheel_path = os.path.join(os.getcwd(), 'whls', 'accessible_output2-0.17-py2.py3-none-any.whl')
    try:
        print_info(f"Installing {module} from wheel")
        subprocess.run([sys.executable, '-m', 'pip', 'install', wheel_path], 
                      check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        try:
            print_info(f"Installing {module} from PyPI")
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                         check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print_info(f"Failed to install {module}")
            return False
    return True

def download_file_to_path(url, path):
    """
    Downloads a file from a URL to a specified local path.
    """
    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            with open(path, 'wb') as f:
                f.write(response.content)
            return True
        except requests.RequestException as e:
            if MONARCH_MODE:
                print_info(f"Download failed for {url}: {e}. Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                print_info(f"Failed to download {url}: {e}")
                return False

def download_folder_github(repo, branch, folder):
    """
    Downloads all files in a GitHub repository folder to a local folder.
    """
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"
    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            files = response.json()
            os.makedirs(folder, exist_ok=True)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(download_file_to_path, file['download_url'], os.path.join(folder, file['name'])) for file in files if file['type'] == 'file']
                concurrent.futures.wait(futures)
            print_info(f"Downloaded folder from GitHub: {folder}")
            return True
        except requests.RequestException as e:
            if MONARCH_MODE:
                print_info(f"Failed to download folder {folder} from GitHub: {e}. Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                print_info(f"Failed to download folder {folder} from GitHub: {e}")
                return False

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
        download_folder_github(GITHUB_REPO, GITHUB_BRANCH, "whls")

def create_mock_imp():
    """
    Creates a mock 'imp' module for Python compatibility.
    """
    class MockImp:
        __name__ = 'imp'
        
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

@lru_cache(maxsize=None)
def get_repo_files_github(repo, branch):
    """
    Gets the list of files in a GitHub repository branch.
    """
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            tree = response.json().get('tree', [])
            return [item['path'] for item in tree if item['type'] == 'blob']
        except requests.RequestException as e:
            if MONARCH_MODE:
                print_info(f"Failed to get repo files from GitHub: {e}. Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                print_info(f"Failed to get repo files from GitHub: {e}")
                return []

def download_file_github(repo, branch, file_path):
    """
    Downloads a single file from a GitHub repository.
    """
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}"
    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            if MONARCH_MODE:
                print_info(f"Failed to download file {file_path} from GitHub: {e}. Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                print_info(f"Failed to download file {file_path} from GitHub: {e}")
                return None

def file_needs_update(local_path, remote_content):
    """
    Checks if a local file needs to be updated with new content.
    """
    if not os.path.exists(local_path):
        return True
    with open(local_path, 'rb') as file:
        return file.read() != remote_content

def is_sound_file(file_path):
    """
    Checks if a file is in the sounds folder and is a sound file.
    """
    return file_path.startswith('sounds/') and file_path.lower().endswith(('.ogg', '.wav', '.mp3'))

def should_skip_file(file_path):
    """
    Determines if a file should be skipped during update.
    """
    # Skip files in the ignored list
    if os.path.basename(file_path) in IGNORED_FILES:
        return True
    
    # Special handling for sound files - only add if not exist
    if is_sound_file(file_path) and os.path.exists(file_path):
        return True
        
    return False

def update_script(script_name):
    """
    Updates the script from GitHub if needed.
    """
    if not AUTO_UPDATE_UPDATER:
        return False
    
    remote_content = download_file_github(GITHUB_REPO, GITHUB_BRANCH, script_name)
    if remote_content is None or not file_needs_update(script_name, remote_content):
        return False

    with open(script_name, 'wb') as file:
        file.write(remote_content)
    print_info(f"Updated script: {script_name}")
    return True

def check_and_update_file(file_path):
    """
    Checks if a file needs to be updated from GitHub.
    """
    # Handle readme.md specially
    if file_path.lower() == 'readme.md':
        readme_content = download_file_github(GITHUB_REPO, GITHUB_BRANCH, file_path)
        if readme_content and file_needs_update('README.txt', readme_content):
            with open('README.txt', 'wb') as file:
                file.write(readme_content)
            print_info("Updated README.txt")
            return True
        return False

    # Check if file should be skipped
    if should_skip_file(file_path):
        print_info(f"Skipping file: {file_path}")
        return False

    # Adjust the filter to ensure all relevant files are considered
    if not file_path.endswith(('.py', '.txt', '.png', '.bat', '.ogg', '.jpg', '.pkl')) and file_path != 'VERSION':
        return False

    remote_content = download_file_github(GITHUB_REPO, GITHUB_BRANCH, file_path)
    if remote_content is None or not file_needs_update(file_path, remote_content):
        return False

    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    
    with open(file_path, 'wb') as file:
        file.write(remote_content)
    print_info(f"Updated file: {file_path}")
    return True

def update_folder_github(repo, branch, folder):
    """
    Updates a folder from a GitHub repository.
    """
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"
    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            remote_files = {file['name'] for file in response.json() if file['type'] == 'file'}
            
            if os.path.exists(folder):
                local_files = set(os.listdir(folder))
                files_to_remove = local_files - remote_files
                
                # Don't remove custom sounds 
                if folder == 'sounds':
                    files_to_remove = set()
                
                for file in files_to_remove:
                    # Skip ignored files
                    if file in IGNORED_FILES:
                        continue
                        
                    os.remove(os.path.join(folder, file))
                    print_info(f"Removed file from {folder} folder: {file}")
                
                return bool(files_to_remove)
            return False
        except requests.RequestException as e:
            if MONARCH_MODE:
                print_info(f"Failed to update {folder} folder from GitHub: {e}. Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                print_info(f"Failed to update {folder} folder from GitHub: {e}")
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
        if download_file_to_path(legendary_url, legendary_path):
            print_info("Legendary downloaded successfully.")
            return True
    except Exception as e:
        print_info(f"Failed to download Legendary: {e}")
    
    return False

def install_requirements():
    """
    Install dependencies listed in requirements.txt more efficiently.
    """
    from importlib.metadata import version, PackageNotFoundError
    from packaging.version import parse as parse_version
    
    def get_package_version(pkg_name):
        try:
            return version(pkg_name)
        except PackageNotFoundError:
            return None
    
    requirements_file = 'requirements.txt'

    # Download requirements.txt if it doesn't exist
    if not os.path.exists(requirements_file):
        print_info(f"{requirements_file} not found. Downloading...")
        requirements_content = download_file_github(GITHUB_REPO, GITHUB_BRANCH, "requirements.txt")
        if requirements_content:
            with open(requirements_file, 'wb') as f:
                f.write(requirements_content)
        else:
            print_info(f"Failed to download {requirements_file}")
            return False

    # Read requirements
    try:
        with open(requirements_file, 'r') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print_info(f"Failed to read {requirements_file}: {e}")
        return False

    # Check what needs to be installed
    missing_packages = []
    upgrade_packages = []
    
    for requirement in requirements:
        # Split package name and version
        if '>=' in requirement:
            pkg_name, version_required = requirement.split('>=')
        elif '==' in requirement:
            pkg_name, version_required = requirement.split('==')
        else:
            pkg_name = requirement
            version_required = None
        
        pkg_name = pkg_name.strip()
        if version_required:
            version_required = version_required.strip()
        
        current_version = get_package_version(pkg_name)
        if current_version is None:
            missing_packages.append(requirement)
        elif version_required and parse_version(current_version) < parse_version(version_required):
            upgrade_packages.append(requirement)

    # Install only if needed
    if not missing_packages and not upgrade_packages:
        return True

    if missing_packages:
        print_info(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install'] + missing_packages,
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            print_info(f"Failed to install missing packages: {e}")
            return False

    if upgrade_packages:
        print_info(f"Upgrading packages: {', '.join(upgrade_packages)}")
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade'] + upgrade_packages,
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as e:
            print_info(f"Failed to upgrade packages: {e}")
            return False

    print_info("Dependencies installed successfully!")
    return True

def get_version_github(repo, branch):
    """
    Fetches the version file from a GitHub repository.
    """
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/VERSION"
    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as e:
            if MONARCH_MODE:
                print_info(f"Failed to fetch VERSION file from GitHub: {e}. Retrying in 2 seconds...")
                time.sleep(2)
                continue
            else:
                print_info(f"Failed to fetch VERSION file from GitHub: {e}")
                return None

def parse_version(version):
    """
    Parses a version string into a tuple of integers.
    """
    return tuple(map(int, version.split('.')))

def check_version():
    """
    Checks if the local version matches the repository version.
    """
    local_version = None
    if os.path.exists('VERSION'):
        with open('VERSION', 'r') as f:
            local_version = f.read().strip()
    
    repo_version = get_version_github(GITHUB_REPO, GITHUB_BRANCH)
    
    if not local_version:
        return True  # No local version, update required
    
    if not repo_version:
        print_info("Failed to fetch repository version. Skipping version check.")
        return False
    
    try:
        local_v = parse_version(local_version)
        repo_v = parse_version(repo_version)
        return local_v != repo_v  # Update if local version is not equal to repo version
    except ValueError:
        print_info("Invalid version format. Treating as update required.")
        return True

def main():
    """
    Main function to run the updater script.
    """
    global MONARCH_MODE
    
    # Parse command line arguments
    args = parse_arguments()
    if args.monarch:
        MONARCH_MODE = True
        print_info("Monarch Mode enabled - will retry failed downloads indefinitely.")
    
    script_name = os.path.basename(__file__)
    
    print_info("Starting FA11y updater...")
    print_info(f"Source: GitHub ({GITHUB_REPO}/{GITHUB_BRANCH})")

    if update_script(script_name):
        print_info("Please restart the updater for updates. Closing in 5 seconds.")
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

    print_info("Checking and installing requirements...")
    requirements_installed = install_requirements()

    if requirements_installed:
        print_info("All requirements installed!")
        if speaker:
            speaker.speak("All requirements installed!")
    else:
        print_info("Some updates may have failed. Please check the console output.")
        if speaker:
            speaker.speak("Some updates may have failed. Please check the console output.")

    # Check and install FakerInput
    print_info("Checking FakerInput installation...")
    fakerinput_success = check_and_install_fakerinput()
    if fakerinput_success:
        if speaker:
            speaker.speak("FakerInput is ready!")
    else:
        print_info("Warning: FakerInput installation failed. Some features may not work properly.")
        if speaker:
            speaker.speak("Warning: FakerInput installation failed.")

    # Ensure to check for updates if version differs
    if not check_version():
        print_info("You are on the latest version of FA11y!")
        if speaker:
            speaker.speak("You are on the latest version of FA11y!")
        sys.exit(0)

    print_info("Checking for updates from GitHub...")
    repo_files = get_repo_files_github(GITHUB_REPO, GITHUB_BRANCH)
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        update_results = list(executor.map(check_and_update_file, repo_files))
        updates_available = any(update_results)

    icons_updated = update_folder_github(GITHUB_REPO, GITHUB_BRANCH, "icons")
    images_updated = update_folder_github(GITHUB_REPO, GITHUB_BRANCH, "images")
    
    # Special handling for sounds folder - only add missing files
    sounds_updated = False
    if 'sounds' not in os.listdir():
        os.makedirs('sounds', exist_ok=True)
        sounds_updated = True
    
    # Check if we need to update the sounds folder by adding missing files
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/sounds?ref={GITHUB_BRANCH}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        remote_sound_files = [file['name'] for file in response.json() if file['type'] == 'file']
        
        existing_sounds = os.listdir('sounds') if os.path.exists('sounds') else []
        
        # Only download sounds that don't exist locally
        for sound_file in remote_sound_files:
            if sound_file not in existing_sounds:
                sound_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/sounds/{sound_file}"
                if download_file_to_path(sound_url, os.path.join('sounds', sound_file)):
                    print_info(f"Added missing sound file: {sound_file}")
                    sounds_updated = True
    except requests.RequestException as e:
        print_info(f"Failed to check sounds folder: {e}")
    
    fa11y_updates = updates_available or icons_updated or images_updated or sounds_updated

    if fa11y_updates:
        print_info("Updates processed.")

    if not check_legendary():
        print_info("Failed to download or find Legendary. Please download it manually and add it to your system PATH.")

    print_info("Update process completed")

    if fa11y_updates:
        closing_message = "FA11y updated! Closing in 5 seconds..."
        if speaker:
            speaker.speak(closing_message)
        print_info(closing_message)
        time.sleep(5)
        sys.exit(1)
    else:
        print_info("Closing in 5 seconds...")
        time.sleep(5)
        sys.exit(0)

if __name__ == "__main__":
    main()
