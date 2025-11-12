"""
FA11y Developer Mode Launcher

Entry point for FA11y developer tools.

Usage:
    python FA11y_dev.py pixel_inspector
    python FA11y_dev.py --list
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.dev.dev_mode import DevMode


def main():
    """Main entry point for dev mode launcher."""
    import argparse

    parser = argparse.ArgumentParser(
        description='FA11y Developer Mode - Extra developer functions and tools',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python FA11y_dev.py pixel_inspector    # Run the pixel inspector tool
    python FA11y_dev.py --list             # List available tools
        """
    )

    parser.add_argument('tool', nargs='?', default='pixel_inspector',
                       help='Tool to run (default: pixel_inspector)')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available developer tools')

    args = parser.parse_args()

    dev_mode = DevMode()

    if args.list:
        dev_mode.list_tools()
    else:
        dev_mode.run_tool(args.tool)


if __name__ == "__main__":
    main()
