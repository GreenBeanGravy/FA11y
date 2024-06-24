import subprocess
import os
import sys
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

def check_python_version():
    major, minor = sys.version_info[:2]
    if (major == 3 and minor in (9, 10)):
        return True
    print(f"You are using Python {major}.{minor}. This script is optimized for Python 3.9 or 3.10.")
    return False

def check_and_install_module(module):
    if importlib.util.find_spec(module) is None:
        print(f"Installing {module}...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                       stdout=subprocess.DEVNULL, 
                       stderr=subprocess.DEVNULL)
        return True  # Module was installed
    return False  # Module was already installed

def install_required_modules():
    modules = ['requests', 'accessible_output2']
    print("Checking and installing required modules...")
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(check_and_install_module, modules))
    
    if any(results):
        print("All required modules have been installed.")
    else:
        print("All required modules were already installed.")

install_required_modules()
import requests
from accessible_output2.outputs.auto import Auto

speaker = Auto()

@lru_cache(maxsize=None)
def get_repo_files(repo, branch='main'):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    response = requests.get(url)
    if response.status_code == 200:
        tree = response.json().get('tree', [])
        return [item['path'] for item in tree if item['type'] == 'blob']
    return []

def download_file(repo, file_path):
    url = f"https://raw.githubusercontent.com/{repo}/main/{file_path}"
    response = requests.get(url)
    return response.content if response.status_code == 200 else None

def file_needs_update(local_path, github_content):
    if not os.path.exists(local_path):
        return True
    with open(local_path, 'rb') as file:
        return file.read() != github_content

def update_script(repo, script_name):
    github_content = download_file(repo, script_name)
    if github_content is None or not file_needs_update(script_name, github_content):
        return False

    choice = input("An update is available for the updater! Apply update? (Y/N): ").strip().lower()
    if choice == 'y':
        with open(script_name, 'wb') as file:
            file.write(github_content)
        print(f"Updated {script_name}")
        return True
    print(f"Update for {script_name} skipped.")
    return False

def check_and_update_file(repo, file_path, script_name, update_mode):
    if file_path.lower() == 'readme.md':
        readme_content = download_file(repo, file_path)
        if readme_content and file_needs_update('README.txt', readme_content):
            if update_mode != 'check':
                with open('README.txt', 'wb') as file:
                    file.write(readme_content)
                print("README updated.")
            return True
        return False

    if not file_path.endswith(('.py', '.txt', '.png')) or file_path.endswith(script_name):
        return False

    if file_path in ('config.txt', 'CUSTOM_POI.txt') and os.path.exists(file_path):
        return False

    github_content = download_file(repo, file_path)
    if github_content is None or not file_needs_update(file_path, github_content):
        return False

    if update_mode == 'check':
        return True

    if update_mode != 'manual':
        directory_name = os.path.dirname(file_path)
        if directory_name:
            os.makedirs(directory_name, exist_ok=True)
        with open(file_path, 'wb') as file:
            file.write(github_content)
        print(f"Updated {file_path}")
    else:
        choice = input(f"Update available for {file_path}. Do you want to update? (Y/N): ").strip().lower()
        if choice == 'y':
            with open(file_path, 'wb') as file:
                file.write(github_content)
            print(f"Updated {file_path}")
        else:
            print(f"Update for {file_path} skipped.")

    return True

def process_updates(repo, repo_files, update_mode, script_name):
    if update_mode == 'skip':
        print("All updates skipped.")
        return False

    with ThreadPoolExecutor() as executor:
        updates = list(executor.map(lambda file_path: check_and_update_file(repo, file_path, script_name, update_mode), repo_files))

    return any(updates)

def main():
    script_name = os.path.basename(__file__)

    if update_script("GreenBeanGravy/FA11y", script_name):
        print("Script updated. Please restart the script to use the updated version.")
        return

    repo_files = get_repo_files("GreenBeanGravy/FA11y")
    
    # Check if any updates are available
    updates_available = any(check_and_update_file("GreenBeanGravy/FA11y", file_path, script_name, 'check')
                            for file_path in repo_files)

    if not updates_available:
        print("You are on the latest version!")
        speaker.speak("You are on the latest version!")
        return

    update_mode = input("Updates are available. Press Enter to update all files automatically, type 'manual' to select updates manually, or type 'skip' to skip updates: ").strip().lower()

    if update_mode == 'skip':
        print("Update process skipped.")
    else:
        updates_processed = process_updates("GreenBeanGravy/FA11y", repo_files, update_mode, script_name)
        if updates_processed:
            speaker.speak("Updates processed.")

    if os.path.exists('requirements.txt'):
        print("Installing packages from requirements.txt...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("All updates applied!")
        speaker.speak("All updates applied!")

if __name__ == "__main__":
    main()