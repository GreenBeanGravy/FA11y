import subprocess
import os
import sys

def install_required_modules():
    print("Checking for required modules...")
    modules = ['requests', 'accessible_output2']
    subprocess.run([sys.executable, '-m', 'pip', 'install'] + modules, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Required modules installed!")

install_required_modules()

import requests
from accessible_output2.outputs.auto import Auto

speaker = Auto()

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

def check_for_updates(repo, script_name):
    repo_files = get_repo_files(repo)
    updates_available = False

    speaker.speak("Checking for updates.")
    update_mode = input("Press Enter to update all files automatically or type 'manual' to select updates manually: ").strip().lower()
    speaker.speak("Processing updates, please wait.")

    for file_path in repo_files:
        if file_path.endswith(('.py', '.txt', '.png')):
            if file_path == 'CUSTOM_POI.txt' and os.path.exists(file_path):
                continue

            if file_path.endswith(script_name):
                continue  # Skip updating the script itself

            github_content = download_file(repo, file_path)
            if github_content is None:
                print(f"Failed to download {file_path} from GitHub.")
                continue

            directory_name = os.path.dirname(file_path)
            if directory_name and not os.path.exists(directory_name):
                os.makedirs(directory_name, exist_ok=True)

            if not os.path.exists(file_path):
                with open(file_path, 'wb') as file:
                    file.write(github_content)
                print(f"New file {file_path} has been downloaded.")
                updates_available = True
            else:
                with open(file_path, 'rb') as file:
                    local_content = file.read()
                if local_content != github_content:
                    updates_available = True
                    if update_mode != 'manual':
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

    if not updates_available:
        print("You are on the latest version!")
        speaker.speak("You are on the latest version!")

def check_python_version():
    if sys.version_info.major == 3 and sys.version_info.minor == 9:
        return True
    else:
        print(f"Python 3.9 is not in use, you are using Python {sys.version_info.major}.{sys.version_info.minor}. Accessible Output 2 requires Python 3.9.x to function properly. Press Enter to install anyways.")
        input()
        return False

def main():
    script_name = os.path.basename(__file__)  # Get the name of the current script
    check_python_version()

    check_for_updates("GreenBeanGravy/FA11y", script_name)
    speaker.speak("Update check complete.")

    if os.path.exists('requirements.txt'):
        print("Installing packages from requirements.txt...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("All updates applied! Press Enter to close the updater.")
        speaker.speak("All updates applied! Press Enter to close the updater.")
        input()

    else:
        print("requirements.txt not found.")

if __name__ == "__main__":
    main()
