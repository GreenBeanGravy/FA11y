import subprocess
import os
import sys

def check_python_version():
    """
    Checks if the current Python version is 3.9.
    If not, prompts the user to continue anyway.
    """
    if sys.version_info.major == 3 and sys.version_info.minor == 9:
        return True
    else:
        print(f"Python 3.9 is not in use, you are using Python version {sys.version_info.major}.{sys.version_info.minor}. Accessible Output 2 requires Python 3.9.x to function properly. Press Enter to install anyways.")
        input()
        return False

def main():
    check_python_version()

    # Install requirements from requirements.txt
    if os.path.exists('requirements.txt'):
        print("Installing packages from requirements.txt...")
        subprocess.run(['pip', 'install', '-r', 'requirements.txt'], check=True)
    else:
        print("requirements.txt not found.")

if __name__ == "__main__":
    main()
