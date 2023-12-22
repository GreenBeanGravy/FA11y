import subprocess
import os
import sys
import requests
from accessible_output2.outputs.auto import Auto

def check_python_version():
    if sys.version_info.major == 3 and sys.version_info.minor == 9:
        return True
    else:
        print(f"You are not using Python 3.9, errors may occur. You are using Python {sys.version_info.major}.{sys.version_info.minor}.")
        return False

def install_required_modules():
    print("Checking for required modules...")
    modules = ['requests', 'accessible_output2']
    subprocess.run([sys.executable, '-m', 'pip', 'install'] + modules, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Required modules installed!")

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

def file_needs_update(local_path, github_content):
    if not os.path.exists(local_path) or open(local_path, 'rb').read() != github_content:
        return True
    return False

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
    else:
        print(f"Update for {script_name} skipped.")
        return False

def check_for_updates(repo, script_name):
    repo_files = get_repo_files(repo)
    updates_available = False

    for file_path in repo_files:
        if file_path.lower() == 'readme.md':
            readme_content = download_file(repo, file_path)
            if readme_content and file_needs_update('README.txt', readme_content):
                with open('README.txt', 'wb') as file:
                    file.write(readme_content)
                print("README updated.")
            continue

        if file_path.endswith(('.py', '.txt', '.png')):
            # Skip 'config.txt' and 'CUSTOM_POI.txt' if they already exist
            if (file_path == 'config.txt' or file_path == 'CUSTOM_POI.txt') and os.path.exists(file_path):
                continue

            if file_path.endswith(script_name):
                continue  # Skip updating the script itself

            github_content = download_file(repo, file_path)
            if github_content is None:
                print(f"Failed to download {file_path} from GitHub.")
                continue

            if file_needs_update(file_path, github_content):
                updates_available = True

    return updates_available

def process_updates(repo, repo_files, update_mode, script_name):
    for file_path in repo_files:
        if file_path.lower() == 'readme.md' or file_path.endswith(script_name):
            continue  # Skip README.md and the script itself

        if file_path.endswith(('.py', '.txt', '.png')):
            if file_path == 'config.txt' and os.path.exists(file_path):
                continue

            # Check if the file is 'CUSTOM_POI.txt' and if it already exists
            if file_path == 'CUSTOM_POI.txt' and os.path.exists(file_path):
                continue  # Do not update 'CUSTOM_POI.txt' if it already exists

            github_content = download_file(repo, file_path)
            if github_content is None or not file_needs_update(file_path, github_content):
                continue

            directory_name = os.path.dirname(file_path)
            if directory_name and not os.path.exists(directory_name):
                os.makedirs(directory_name, exist_ok=True)

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

def main():
    script_name = os.path.basename(__file__)  # Get the name of the current script

    # First, check if the script itself needs an update
    if update_script("GreenBeanGravy/FA11y", script_name):
        print("Script updated. Please restart the script to use the updated version.")
        return

    install_required_modules()

    if check_for_updates("GreenBeanGravy/FA11y", script_name):
        update_mode = input("Updates available. Press Enter to update all files automatically or type 'manual' to select updates manually: ").strip().lower()
        process_updates("GreenBeanGravy/FA11y", get_repo_files("GreenBeanGravy/FA11y"), update_mode, script_name)
        speaker.speak("Updates processed.")
    else:
        print("You are on the latest version!")
        speaker.speak("You are on the latest version!")

    if os.path.exists('requirements.txt'):
        print("Installing packages from requirements.txt...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("All updates applied!")
        speaker.speak("All updates applied!")

if __name__ == "__main__":
    main()
