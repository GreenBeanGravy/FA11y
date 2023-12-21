import subprocess
import os
import sys
import requests
import shutil
from accessible_output2.outputs.auto import Auto

def check_python_version():
    if sys.version_info.major == 3 and sys.version_info.minor == 9:
        return True
    else:
        print(f"Python 3.9 is not in use. You are using Python {sys.version_info.major}.{sys.version_info.minor}.")
        return False

if not check_python_version():
    sys.exit(1)

def install_required_modules():
    print("Checking for required modules...")
    modules = ['requests', 'accessible_output2']
    subprocess.run([sys.executable, '-m', 'pip', 'install'] + modules, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Required modules installed!")

install_required_modules()

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

def check_for_updates(repo, script_name):
    repo_files = get_repo_files(repo)
    updates_available = False
    script_updated = False

    for file_path in repo_files:
        if file_path.lower() == 'readme.md':
            readme_content = download_file(repo, file_path)
            if readme_content and file_needs_update('README.txt', readme_content):
                with open('README.txt', 'wb') as file:
                    file.write(readme_content)
                print("README updated.")
            continue

        if file_path.endswith(('.py', '.txt', '.png')):
            if file_path == 'config.txt' and os.path.exists(file_path):
                continue

            github_content = download_file(repo, file_path)
            if github_content is None:
                print(f"Failed to download {file_path} from GitHub.")
                continue

            if file_needs_update(file_path, github_content):
                updates_available = True
                if file_path.endswith(script_name):
                    script_updated = True

    return updates_available, script_updated

def process_updates(repo, repo_files, update_mode, script_name):
    for file_path in repo_files:
        if file_path.lower() == 'readme.md':
            continue  # Skip README.md

        if file_path.endswith(('.py', '.txt', '.png')):
            if file_path == 'config.txt' and os.path.exists(file_path):
                continue

            github_content = download_file(repo, file_path)
            if github_content is None or not file_needs_update(file_path, github_content):
                continue

            if update_mode != 'manual' or (update_mode == 'manual' and user_confirms_update(file_path)):
                apply_update(file_path, github_content)
                print(f"Updated {file_path}")

def user_confirms_update(file_path):
    choice = input(f"Update available for {file_path}. Do you want to update? (Y/N): ").strip().lower()
    return choice == 'y'

def apply_update(file_path, github_content):
    with open(file_path, 'wb') as file:
        file.write(github_content)

def update_self_and_restart(repo, script_name):
    github_content = download_file(repo, script_name)
    if github_content is None:
        return

    temp_file = script_name + '.temp'
    with open(temp_file, 'wb') as file:
        file.write(github_content)

    os.replace(temp_file, script_name)
    python = sys.executable
    os.execl(python, python, *sys.argv)

def main():
    script_name = os.path.basename(__file__)
    check_python_version()

    updates_available, script_updated = check_for_updates("GreenBeanGravy/FA11y", script_name)

    if updates_available:
        update_mode = input("Updates available. Press Enter to update all files automatically or type 'manual' to select updates manually: ").strip().lower()
        process_updates("GreenBeanGravy/FA11y", get_repo_files("GreenBeanGravy/FA11y"), update_mode, script_name)

        if script_updated:
            update_self_and_restart("GreenBeanGravy/FA11y", script_name)
            return  # The script will restart after this line

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
