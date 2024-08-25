import os
import sys
import subprocess
import importlib.util
from functools import lru_cache
import shutil
import time
import concurrent.futures
import requests

# Set the command window title
os.system("title FA11y")

# Suppress Pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# Configuration
AUTO_UPDATE_UPDATER = True
MAX_RESTARTS = 3

def print_info(message):
    print(message)

def check_and_install_module(module):
    try:
        if importlib.util.find_spec(module) is None:
            print_info(f"Installing module: {module}")
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                           check=True, capture_output=True)
            return True
        return False
    except subprocess.CalledProcessError:
        print_info(f"Failed to install module: {module}")
        return False

def install_required_modules():
    modules = ['requests', 'psutil']
    
    # Check for pywin32
    try:
        import win32api
    except ImportError:
        modules.append('pywin32')
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(check_and_install_module, modules))
    
    return any(results)

def install_accessible_output2():
    module = 'accessible_output2'
    if importlib.util.find_spec(module) is None:
        wheel_path = os.path.join(os.getcwd(), 'whls', 'accessible_output2-0.17-py2.py3-none-any.whl')
        try:
            print_info(f"Installing {module} from wheel")
            subprocess.run([sys.executable, '-m', 'pip', 'install', wheel_path], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            try:
                print_info(f"Installing {module} from PyPI")
                subprocess.run([sys.executable, '-m', 'pip', 'install', module], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                print_info(f"Failed to install {module}")
                return False
    return True

def download_file_to_path(url, path):
    response = requests.get(url)
    response.raise_for_status()
    with open(path, 'wb') as f:
        f.write(response.content)

def download_folder(repo, branch, folder):
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        files = response.json()
        os.makedirs(folder, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for file in files:
                if file['type'] == 'file':
                    file_url = file['download_url']
                    file_path = os.path.join(folder, file['name'])
                    futures.append(executor.submit(download_file_to_path, file_url, file_path))
            concurrent.futures.wait(futures)
        print_info(f"Downloaded folder: {folder}")
    except requests.RequestException as e:
        print_info(f"Failed to download folder {folder}: {e}")
        sys.exit(1)

def install_required_modules_and_whls():
    restart_count = int(os.environ.get('UPDATER_RESTART_COUNT', 0))
    if restart_count >= MAX_RESTARTS:
        print_info(f"Maximum restarts ({MAX_RESTARTS}) reached. Continuing without further restarts.")
        return

    if install_required_modules():
        print_info("New modules installed. Restarting updater.")
        os.environ['UPDATER_RESTART_COUNT'] = str(restart_count + 1)
        os.execv(sys.executable, ['python'] + sys.argv)
    
    if not os.path.exists('whls'):
        download_folder("GreenBeanGravy/FA11y", "main", "whls")

def create_mock_imp():
    class MockImp:
        __name__ = 'imp'
        
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

print_info("Starting updater!")
install_required_modules_and_whls()
ao2_available = install_accessible_output2()

if sys.version_info >= (3, 12):
    create_mock_imp()

speaker = None
if ao2_available:
    try:
        from accessible_output2.outputs.auto import Auto
        speaker = Auto()
    except ImportError:
        print_info("Failed to import accessible_output2. Speech output will be unavailable.")

@lru_cache(maxsize=None)
def get_repo_files(repo, branch='main'):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tree = response.json().get('tree', [])
        return [item['path'] for item in tree if item['type'] == 'blob']
    except requests.RequestException as e:
        print_info(f"Failed to get repo files: {e}")
        return []

def download_file(repo, file_path):
    url = f"https://raw.githubusercontent.com/{repo}/main/{file_path}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        print_info(f"Failed to download file {file_path}: {e}")
        return None

def file_needs_update(local_path, github_content):
    if not os.path.exists(local_path):
        return True
    with open(local_path, 'rb') as file:
        return file.read() != github_content

def update_script(repo, script_name):
    if not AUTO_UPDATE_UPDATER:
        return False
    github_content = download_file(repo, script_name)
    if github_content is None or not file_needs_update(script_name, github_content):
        return False

    with open(script_name, 'wb') as file:
        file.write(github_content)
    print_info(f"Updated script: {script_name}")
    return True

def check_and_update_file(repo, file_path, script_name):
    if file_path.lower() == 'readme.md':
        readme_content = download_file(repo, file_path)
        if readme_content and file_needs_update('README.txt', readme_content):
            with open('README.txt', 'wb') as file:
                file.write(readme_content)
            print_info("Updated README.txt")
            return True
        return False

    if not file_path.endswith(('.py', '.txt', '.png', '.bat', '.ogg', '.jpg')) and file_path != 'VERSION':
        return False

    if file_path in ('config.txt', 'CUSTOM_POI.txt') and os.path.exists(file_path):
        return False

    github_content = download_file(repo, file_path)
    if github_content is None or not file_needs_update(file_path, github_content):
        return False

    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    
    with open(file_path, 'wb') as file:
        file.write(github_content)
    print_info(f"Updated file: {file_path}")
    return True

def update_folder(repo, folder, branch='main'):
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"

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

def process_updates(repo, repo_files, script_name):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        updates = list(executor.map(lambda file_path: check_and_update_file(repo, file_path, script_name), repo_files))
    return any(updates)

def check_legendary():
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
    if not os.path.exists('requirements.txt'):
        print_info("requirements.txt not found. Downloading from GitHub...")
        url = "https://raw.githubusercontent.com/GreenBeanGravy/FA11y/main/requirements.txt"
        try:
            download_file_to_path(url, 'requirements.txt')
            print_info("requirements.txt downloaded successfully.")
        except Exception as e:
            print_info(f"Failed to download requirements.txt: {e}")
            return False

    print_info("Installing requirements...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                       check=True, capture_output=True, text=True)
        print_info("Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_info(f"Failed to install requirements: {e}")
        return False

def get_version(repo):
    url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print_info(f"Failed to fetch VERSION file: {e}")
        return None

def parse_version(version):
    return tuple(map(int, version.split('.')))

def check_version():
    repo = "GreenBeanGravy/FA11y"
    local_version = None
    if os.path.exists('VERSION'):
        with open('VERSION', 'r') as f:
            local_version = f.read().strip()
    
    repo_version = get_version(repo)
    
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
    script_name = os.path.basename(__file__)

    if update_script("GreenBeanGravy/FA11y", script_name):
        if speaker:
            speaker.speak("Please restart the updater for updates. Closing in 5 seconds.")
        print_info("Please restart the updater for updates. Closing in 5 seconds.")
        time.sleep(5)
        sys.exit(0)

    update_required = check_version()
    if not update_required:
        if speaker:
            speaker.speak("You are on the latest version of FA11y!")
        print_info("You are on the latest version of FA11y!")
        if '--run-by-fa11y' in sys.argv:
            sys.exit(0)  # Exit immediately if run by FA11y
        else:
            time.sleep(3)
        sys.exit(0)

    repo_files = get_repo_files("GreenBeanGravy/FA11y")
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        update_results = list(executor.map(lambda file_path: check_and_update_file("GreenBeanGravy/FA11y", file_path, script_name), repo_files))
        updates_available = any(update_results)

    icons_updated = update_folder("GreenBeanGravy/FA11y", "icons")
    images_updated = update_folder("GreenBeanGravy/FA11y", "images")
    fa11y_updates = updates_available or icons_updated or images_updated

    if fa11y_updates:
        print_info("Updates processed.")

    print_info("Checking and installing requirements...")
    requirements_installed = install_requirements()

    if requirements_installed:
        if speaker:
            speaker.speak("All updates applied!")
        print_info("All updates applied!")
    else:
        if speaker:
            speaker.speak("Some updates may have failed. Please check the console output.")
        print_info("Some updates may have failed. Please check the console output.")

    legendary_exists = check_legendary()
    if not legendary_exists:
        print_info("Failed to download or find Legendary. Please download it manually and add it to your system PATH.")

    print_info("Update process completed")

    if fa11y_updates:
        closing_message = "FA11y updated! Closing in 5 seconds..."
        if speaker:
            speaker.speak(closing_message)
        print_info(closing_message)
        time.sleep(5)
        sys.exit(1)  # Exit with code 1 to indicate updates were applied
    else:
        print_info("Closing in 5 seconds...")
        time.sleep(5)
        sys.exit(0)  # Exit with code 0 to indicate no updates were applied

if __name__ == "__main__":
    main()
