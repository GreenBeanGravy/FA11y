import subprocess
import os
import sys
import importlib.util
from functools import lru_cache
import shutil
import time
import concurrent.futures
import psutil
import hashlib

# Configuration
AUTO_UPDATE_UPDATER = True  # Set to False to disable auto-updates of the updater script

def print_info(message):
    print(message)

def check_and_install_module(module):
    try:
        if importlib.util.find_spec(module) is None:
            print_info(f"Installing module: {module}")
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False
    except subprocess.CalledProcessError:
        print_info(f"Failed to install module: {module}")
        return False

def install_required_modules():
    modules = ['requests', 'concurrent.futures', 'pywintypes', 'pywin32', 'psutil']
    for module in modules:
        check_and_install_module(module)

def install_accessible_output2():
    module = 'accessible_output2'
    if importlib.util.find_spec(module) is None:
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

def download_folder(repo, branch, folder):
    import requests
    url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        files = response.json()
        if not os.path.exists(folder):
            os.makedirs(folder)
        for file in files:
            if file['type'] == 'file':
                file_url = file['download_url']
                file_path = os.path.join(folder, file['name'])
                file_content = requests.get(file_url).content
                with open(file_path, 'wb') as f:
                    f.write(file_content)
        print_info(f"Downloaded folder: {folder}")
    except requests.RequestException as e:
        print_info(f"Failed to download folder {folder}: {e}")
        sys.exit(1)

def install_required_modules_and_whls():
    install_required_modules()
    if not os.path.exists('whls'):
        download_folder("GreenBeanGravy/FA11y", "main", "whls")

def create_mock_imp():
    class MockImp:
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

print_info("Starting updater script")
install_required_modules_and_whls()
ao2_available = install_accessible_output2()

if sys.version_info >= (3, 12):
    create_mock_imp()

import requests
from concurrent.futures import ThreadPoolExecutor

if ao2_available:
    try:
        from accessible_output2.outputs.auto import Auto
        speaker = Auto()
        print_info("Accessible output initialized")
    except ImportError:
        print_info("Failed to import accessible_output2. Speech output will be unavailable.")
        speaker = None
else:
    speaker = None

def get_file_sha(repo, file_path, branch='main'):
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={branch}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('sha')
    except requests.RequestException:
        return None

@lru_cache(maxsize=None)
def get_repo_files(repo, branch='main'):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tree = response.json().get('tree', [])
        return [(item['path'], item['sha']) for item in tree if item['type'] == 'blob']
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

def get_local_file_sha(file_path):
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha1.update(data)
    return sha1.hexdigest()

def file_needs_update(local_path, github_sha):
    if not os.path.exists(local_path):
        return True
    local_sha = get_local_file_sha(local_path)
    return local_sha != github_sha

def update_script(repo, script_name):
    if not AUTO_UPDATE_UPDATER:
        return False
    github_sha = get_file_sha(repo, script_name)
    if github_sha is None or not file_needs_update(script_name, github_sha):
        return False

    github_content = download_file(repo, script_name)
    if github_content is None:
        return False

    with open(script_name, 'wb') as file:
        file.write(github_content)
    print_info(f"Updated script: {script_name}")
    return True

def check_and_update_file(repo, file_path, file_sha, script_name):
    if file_path.lower() == 'readme.md':
        readme_content = download_file(repo, file_path)
        if readme_content and file_needs_update('README.txt', file_sha):
            with open('README.txt', 'wb') as file:
                file.write(readme_content)
            print_info("Updated README.txt")
            return True
        return False

    if not file_path.endswith(('.py', '.txt', '.png', '.bat')) or file_path.endswith(script_name):
        return False

    if file_path in ('config.txt', 'CUSTOM_POI.txt') and os.path.exists(file_path):
        return False

    if file_needs_update(file_path, file_sha):
        github_content = download_file(repo, file_path)
        if github_content is None:
            return False

        directory_name = os.path.dirname(file_path)
        if directory_name:
            os.makedirs(directory_name, exist_ok=True)
        with open(file_path, 'wb') as file:
            file.write(github_content)
        print_info(f"Updated file: {file_path}")
        return True
    return False

def update_icons_folder(repo, branch='main'):
    folder = "icons"
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
                print_info(f"Removed file from icons folder: {file}")
            
            return len(files_to_remove) > 0
        else:
            return False
    except requests.RequestException as e:
        print_info(f"Failed to update icons folder: {e}")
        return False

def process_updates(repo, repo_files, script_name):
    with ThreadPoolExecutor() as executor:
        updates = list(executor.map(lambda x: check_and_update_file(repo, x[0], x[1], script_name), repo_files))
    return any(updates)

def is_legendary_in_path():
    return shutil.which('legendary') is not None

def verify_legendary():
    if is_legendary_in_path():
        print_info("Legendary found in system PATH.")
        if speaker:
            speaker.speak("Legendary is already installed.")
        return True

    local_path = os.path.join(os.getcwd(), "legendary.exe")
    if os.path.exists(local_path):
        print_info("legendary.exe found in the current directory.")
        if speaker:
            speaker.speak("Legendary is already downloaded.")
        return True

    LEGENDARY_URL = "https://github.com/derrod/legendary/releases/download/0.20.34/legendary.exe"
    print_info("legendary.exe not found. Attempting to download...")
    if speaker:
        speaker.speak("Legendary not found. Attempting to download.")
    
    try:
        response = requests.get(LEGENDARY_URL)
        response.raise_for_status()
        with open(local_path, 'wb') as file:
            file.write(response.content)
        print_info("Downloaded legendary.exe")
        if speaker:
            speaker.speak("Legendary has been downloaded.")
        return True
    except requests.RequestException as e:
        print_info(f"Failed to download legendary.exe: {e}")
        if speaker:
            speaker.speak("Failed to download Legendary.")
        return False

def close_fa11y():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == 'FA11y.exe' or proc.info['name'] == 'python.exe':
            try:
                cmdline = proc.cmdline()
                if 'FA11y.py' in cmdline or 'FA11y.exe' in cmdline:
                    proc.terminate()
                    proc.wait(timeout=5)
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
    return False

def main():
    script_name = os.path.basename(__file__)
    instant_close = '--instant-close' in sys.argv
    run_by_fa11y = '--run-by-fa11y' in sys.argv

    if update_script("GreenBeanGravy/FA11y", script_name):
        if speaker:
            speaker.speak("Script updated. Please restart the script to use the updated version.")
        print_info("Script updated. Please restart the script to use the updated version.")
        time.sleep(5)
        sys.exit()

    repo_files = get_repo_files("GreenBeanGravy/FA11y")
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        update_results = list(executor.map(lambda x: check_and_update_file("GreenBeanGravy/FA11y", x[0], x[1], script_name), repo_files))
        updates_available = any(update_results)

    icons_updated = update_icons_folder("GreenBeanGravy/FA11y")

    legendary_verified = verify_legendary()

    if not updates_available and not icons_updated and legendary_verified:
        if speaker:
            speaker.speak("You are on the latest version!")
        print_info("You are on the latest version!")
        time.sleep(5)
        sys.exit()

    updates_processed = process_updates("GreenBeanGravy/FA11y", repo_files, script_name)

    if updates_processed or icons_updated:
        if speaker:
            speaker.speak("Updates processed.")
        print_info("Updates processed.")

    if os.path.exists('requirements.txt'):
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if speaker:
                speaker.speak("All updates applied!")
            print_info("All updates applied!")
        except subprocess.CalledProcessError as e:
            print_info(f"Failed to install requirements: {e}")

    print_info("Update process completed")

    if updates_available or icons_updated:
        if speaker:
            speaker.speak("Updates are available. FA11y needs to be restarted.")
        print_info("Updates are available. FA11y needs to be restarted.")
        
        if run_by_fa11y:
            print_info("Attempting to close FA11y...")
            time.sleep(2)  # Give some time for FA11y to finish its operations
            if close_fa11y():
                print_info("Successfully closed FA11y.")
                if speaker:
                    speaker.speak("FA11y has been closed. Please restart it to apply updates.")
            else:
                print_info("Failed to close FA11y automatically.")
                if speaker:
                    speaker.speak("Failed to close FA11y automatically. Please restart it manually to apply updates.")
        else:
            if speaker:
                speaker.speak("Please restart FA11y to apply updates. Closing in 7 seconds.")
            print_info("Please restart FA11y to apply updates. Closing in 7 seconds.")
            time.sleep(7)
    else:
        print_info("Closing in 5 seconds...")
        time.sleep(5)

    sys.exit()

if __name__ == "__main__":
    main()
