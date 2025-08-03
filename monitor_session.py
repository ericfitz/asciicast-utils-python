#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///

import argparse
import sys
import urllib.parse
import webbrowser
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Connect to terminal monitoring session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  monitor_session.py http://localhost:8888
  monitor_session.py --browser firefox http://192.168.1.100:8888
  monitor_session.py --no-open http://server.example.com:9999
        """
    )
    
    parser.add_argument(
        "url", 
        help="Monitor server URL (http://host:port)"
    )
    
    parser.add_argument(
        "--browser", 
        help="Browser to use (chrome, firefox, safari, default)"
    )
    
    parser.add_argument(
        "--no-open", 
        action="store_true", 
        help="Don't auto-open browser, just show URL"
    )
    
    args = parser.parse_args()
    
    # Validate URL format
    parsed_url = urllib.parse.urlparse(args.url)
    if not parsed_url.scheme or not parsed_url.netloc:
        print(f"Error: Invalid URL format: {args.url}")
        print("Expected format: http://hostname:port")
        sys.exit(1)
    
    # Ensure http scheme
    if parsed_url.scheme not in ['http', 'https']:
        print(f"Error: URL must use http:// or https:// scheme: {args.url}")
        sys.exit(1)
    
    if args.no_open:
        print(f"Monitor URL: {args.url}")
        print("Open this URL in your browser to view the terminal session.")
        print("The monitor will show recent output and then live updates.")
    else:
        print(f"Opening monitor session: {args.url}")
        
        success = False
        if args.browser:
            # Try to use specific browser
            browser_map = {
                'chrome': 'google-chrome',
                'firefox': 'firefox', 
                'safari': 'safari',
                'edge': 'microsoft-edge'
            }
            browser_cmd = browser_map.get(args.browser.lower(), args.browser)
            
            try:
                controller = webbrowser.get(browser_cmd)
                controller.open(args.url)
                success = True
                print(f"Opened in {args.browser}")
            except webbrowser.Error:
                print(f"Warning: Could not open {args.browser}, trying default browser...")
        
        if not success:
            try:
                webbrowser.open(args.url)
                print("Opened in default browser")
                success = True
            except webbrowser.Error:
                print("Error: Could not open browser automatically")
                success = False
        
        if success:
            print("\nBrowser opened. If the session is active, you should see:")
            print("  - Connection status at the top")
            print("  - Recent terminal output (if joining mid-session)")
            print("  - Live terminal updates")
            print("  - Session information (shell, start time)")
            print("\nPress Ctrl+C to exit this utility (won't affect the session).")
            
            try:
                input()  # Keep utility running
            except KeyboardInterrupt:
                print("\nMonitor utility exiting.")
        else:
            print(f"\nManually open this URL in your browser: {args.url}")


if __name__ == "__main__":
    main()