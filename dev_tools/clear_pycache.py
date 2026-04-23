import os
import shutil
import sys

def remove_pycache(start_path='.'):
    """
    Recursively walks through directories starting at start_path
    and deletes any folder named '__pycache__'.
    """
    # Verify the path exists
    if not os.path.exists(start_path):
        print(f"Error: The path '{start_path}' does not exist.")
        return

    print(f"Scanning for __pycache__ folders in: {os.path.abspath(start_path)}...\n")
    
    deleted_count = 0

    # os.walk allows us to look at every subdirectory recursively
    for root, dirs, files in os.walk(start_path):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                # shutil.rmtree removes a directory and all its contents
                shutil.rmtree(pycache_path)
                print(f"Deleted: {pycache_path}")
                deleted_count += 1
                
                # Remove it from dirs so os.walk doesn't try to enter it
                dirs.remove('__pycache__')
            except Exception as e:
                print(f"Failed to delete {pycache_path}. Reason: {e}")

    if deleted_count == 0:
        print("\nNo __pycache__ folders found.")
    else:
        print(f"\nCleanup complete. Removed {deleted_count} folder(s).")

if __name__ == "__main__":
    # Uses the current directory by default, or the first argument if provided
    target_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    remove_pycache(target_dir)