import subprocess
import os
import sys
import importlib.util
from functools import lru_cache
import shutil

def check_and_install_module(module):
    try:
        if importlib.util.find_spec(module) is None:
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False
    except subprocess.CalledProcessError:
        return False

def install_required_modules():
    modules = ['requests', 'concurrent.futures']
    for module in modules:
        check_and_install_module(module)

def install_accessible_output2():
    module = 'accessible_output2'
    if importlib.util.find_spec(module) is None:
        wheel_path = os.path.join(os.getcwd(), 'whls', 'accessible_output2-0.17-py2.py3-none-any.whl')
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', wheel_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', module], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
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
    except requests.RequestException:
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

install_required_modules_and_whls()
ao2_available = install_accessible_output2()

if sys.version_info >= (3, 12):
    create_mock_imp()

import requests
from concurrent.futures import ThreadPoolExecutor

if ao2_available:
    from accessible_output2.outputs.auto import Auto
    speaker = Auto()
else:
    speaker = None

@lru_cache(maxsize=None)
def get_repo_files(repo, branch='main'):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tree = response.json().get('tree', [])
        return [item['path'] for item in tree if item['type'] == 'blob']
    except requests.RequestException:
        return []

def download_file(repo, file_path):
    url = f"https://raw.githubusercontent.com/{repo}/main/{file_path}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        return None

def file_needs_update(local_path, github_content):
    if not os.path.exists(local_path):
        return True
    with open(local_path, 'rb') as file:
        return file.read() != github_content

def update_script(repo, script_name):
    github_content = download_file(repo, script_name)
    if github_content is None or not file_needs_update(script_name, github_content):
        return False

    with open(script_name, 'wb') as file:
        file.write(github_content)
    return True

def check_and_update_file(repo, file_path, script_name):
    if file_path.lower() == 'readme.md':
        readme_content = download_file(repo, file_path)
        if readme_content and file_needs_update('README.txt', readme_content):
            with open('README.txt', 'wb') as file:
                file.write(readme_content)
            return True
        return False

    if not file_path.endswith(('.py', '.txt', '.png')) or file_path.endswith(script_name):
        return False

    if file_path in ('config.txt', 'CUSTOM_POI.txt') and os.path.exists(file_path):
        return False

    github_content = download_file(repo, file_path)
    if github_content is None or not file_needs_update(file_path, github_content):
        return False

    directory_name = os.path.dirname(file_path)
    if directory_name:
        os.makedirs(directory_name, exist_ok=True)
    with open(file_path, 'wb') as file:
        file.write(github_content)
    return True

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
            
            return len(files_to_remove) > 0
        else:
            return False
    except requests.RequestException:
        return False

def process_updates(repo, repo_files, script_name):
    with ThreadPoolExecutor() as executor:
        updates = list(executor.map(lambda file_path: check_and_update_file(repo, file_path, script_name), repo_files))

    return any(updates)

def is_legendary_in_path():
    return shutil.which('legendary') is not None

def verify_legendary():
    if is_legendary_in_path():
        print("legendary.exe found in PATH.")
        if speaker:
            speaker.speak("Legendary is already installed.")
        
        try:
            subprocess.run(['legendary', '--version'], check=True, capture_output=True)
            print("Verified legendary.exe functionality.")
            if speaker:
                speaker.speak("Legendary is working properly.")
            return True
        except subprocess.CalledProcessError:
            print("legendary.exe found in PATH but failed to execute.")
            if speaker:
                speaker.speak("Legendary is installed but not working properly.")
            return False
    else:
        print("legendary.exe not found in PATH.")
        if speaker:
            speaker.speak("Legendary is not installed.")
        return False

def main():
    script_name = os.path.basename(__file__)

    if update_script("GreenBeanGravy/FA11y", script_name):
        if speaker:
            speaker.speak("Script updated. Please restart the script to use the updated version.")
        print("Script updated. Please restart the script to use the updated version.")
        return

    repo_files = get_repo_files("GreenBeanGravy/FA11y")
    
    updates_available = any(check_and_update_file("GreenBeanGravy/FA11y", file_path, script_name)
                            for file_path in repo_files)

    icons_updated = update_icons_folder("GreenBeanGravy/FA11y")

    legendary_verified = verify_legendary()

    if not updates_available and not icons_updated and legendary_verified:
        if speaker:
            speaker.speak("You are on the latest version!")
        print("You are on the latest version!")
        return

    updates_processed = process_updates("GreenBeanGravy/FA11y", repo_files, script_name)

    if updates_processed or icons_updated:
        if speaker:
            speaker.speak("Updates processed.")
        print("Updates processed.")

    if os.path.exists('requirements.txt'):
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if speaker:
                speaker.speak("All updates applied!")
            print("All updates applied!")
        except subprocess.CalledProcessError:
            pass

if __name__ == "__main__":
    main()
