import subprocess
import os
import sys
import importlib.util
from functools import lru_cache

def check_and_install_module(module):
    try:
        if importlib.util.find_spec(module) is None:
            print(f"Installing {module}...")
            subprocess.run([sys.executable, '-m', 'pip', 'install', module], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False
    except subprocess.CalledProcessError:
        print(f"Failed to install {module}. Please install it manually.")
        return False

def install_required_modules():
    modules = ['requests', 'concurrent.futures']
    print("Checking and installing required modules...")
    for module in modules:
        check_and_install_module(module)
    print("All required modules have been checked.")

def install_accessible_output2():
    module = 'accessible_output2'
    if importlib.util.find_spec(module) is None:
        print(f"{module} not found. Attempting to install from whl file...")
        wheel_path = os.path.join(os.getcwd(), 'whls', 'accessible_output2-0.17-py2.py3-none-any.whl')
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', wheel_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"{module} installed successfully from whl file.")
        except subprocess.CalledProcessError:
            print(f"Failed to install {module} from whl file. Attempting to install using pip...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', module], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                print(f"{module} installed successfully using pip.")
            except subprocess.CalledProcessError:
                print(f"Failed to install {module} using pip.")
                return False
        return True
    return False

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
        print(f"{folder} folder downloaded successfully.")
    except requests.RequestException as e:
        print(f"Failed to download {folder} folder. Error: {e}")
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
install_accessible_output2()

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    create_mock_imp()

# Now that we've ensured all required modules are installed and mocked if necessary, we can safely import them
import requests
from concurrent.futures import ThreadPoolExecutor
from accessible_output2.outputs.auto import Auto

speaker = Auto()

@lru_cache(maxsize=None)
def get_repo_files(repo, branch='main'):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = requests.get(url)
        response.raise_for_status()
        tree = response.json().get('tree', [])
        return [item['path'] for item in tree if item['type'] == 'blob']
    except requests.RequestException as e:
        print(f"Failed to fetch repository files. Error: {e}")
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

    directory_name = os.path.dirname(file_path)
    if directory_name:
        os.makedirs(directory_name, exist_ok=True)
    with open(file_path, 'wb') as file:
        file.write(github_content)
    print(f"Updated {file_path}")
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
                print(f"Removed {file} from icons folder.")
            
            return len(files_to_remove) > 0
        else:
            return False
    except requests.RequestException as e:
        print(f"Failed to fetch icons folder contents. Error: {e}")
        return False

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

    # Update icons folder
    icons_updated = update_icons_folder("GreenBeanGravy/FA11y")

    if not updates_available and not icons_updated:
        print("You are on the latest version!")
        speaker.speak("You are on the latest version!")
        return

    update_mode = input("Updates are available. Press Enter to update all files automatically, or type 'skip' to skip updates: ").strip().lower()

    if update_mode == 'skip':
        print("Update process skipped.")
    else:
        updates_processed = process_updates("GreenBeanGravy/FA11y", repo_files, update_mode, script_name)
        if updates_processed or icons_updated:
            speaker.speak("Updates processed.")

    if os.path.exists('requirements.txt'):
        print("Installing packages from requirements.txt...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("All updates applied!")
            speaker.speak("All updates applied!")
        except subprocess.CalledProcessError:
            print("Failed to install packages from requirements.txt. Please install them manually.")

if __name__ == "__main__":
    main()