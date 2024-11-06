from lib.guis.AccessibleUIBackend import AccessibleUIBackend
import requests
import json
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import time
import pyautogui
from lib.utilities import force_focus_window

class FortniteIslandSearch:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1'
        }

    def extract_islands_from_json(self, json_data: Dict) -> List[Dict]:
        """Extract island information from JSON response."""
        islands = []
        try:
            # First try to get islands directly 
            items = json_data.get('state', {}).get('loaderData', {}).get('routes/_search.search._index', {}).get('results', {}).get('islands', {}).get('items', [])
            
            # If no items found, try getting from 'all' section
            if not items:
                items = json_data.get('state', {}).get('loaderData', {}).get('routes/_search.search._index', {}).get('results', {}).get('all', {}).get('items', [])
                
                for item in items:
                    code_match = re.search(r'/(\d{4}-\d{4}-\d{4})\?', item.get('link', ''))
                    code = code_match.group(1) if code_match else ''
                    
                    title = item.get('title', '')
                    title = title.split(' by ')[0]
                    title = re.sub(r'\s+\d{4}-\d{4}-\d{4}.*$', '', title)
                    
                    processed_item = {
                        'title': title,
                        'code': code,
                        'playerCount': 0,
                        'description': item.get('snippet', '')
                    }
                    islands.append(processed_item)
            else:
                for island in items:
                    processed_island = {
                        'title': island.get('title', ''),
                        'code': island.get('islandCode', ''),
                        'playerCount': island.get('ccu', 0),
                        'description': island.get('imgAlt', '')
                    }
                    islands.append(processed_island)
            
            return islands
        except Exception as e:
            print(f"Error extracting islands: {str(e)}")
            return []

    def search_islands(self, query: str, page: int = 1, lang: str = "en-US") -> Tuple[List[Dict], bool]:
        url = "https://www.fortnite.com/search"
        params = {
            'q': query,
            'lang': lang,
            'page': page
        }

        try:
            response = self.session.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            
            pattern = r'window\.__remixContext\s*=\s*({.*?});'
            match = re.search(pattern, response.text, re.DOTALL)
            if not match:
                raise ValueError("Could not find __remixContext in response")

            json_data = json.loads(match.group(1))
            islands = self.extract_islands_from_json(json_data)
            
            results = json_data.get('state', {}).get('loaderData', {}).get('routes/_search.search._index', {}).get('results', {})
            has_next = results.get('islands', {}).get('hasNext', False) or results.get('all', {}).get('hasNext', False)
            
            return islands, has_next
        except Exception as e:
            print(f"Search error: {str(e)}")
            return [], False

class IslandSelectorGUI:
    def __init__(self):
        self.searcher = FortniteIslandSearch()
        self.current_page = 1
        self.current_query = ""
        self.current_islands = []
        self.has_next_page = False
        self.ui = AccessibleUIBackend("Island Selector")
        self.setup_ui()

    def is_valid_island_code(self, code: str) -> bool:
        """Check if the island code matches the expected format (1111-1111-1111)."""
        return bool(re.match(r'^\d{4}-\d{4}-\d{4}$', code))

    def setup_ui(self):
        """Initialize the UI with search and results tabs."""
        self.ui.add_tab("Search")
        self.ui.add_tab("Results")
        
        # Add search entry
        self.ui.add_entry("Search", "Search Query")
        self.ui.add_button("Search", "Search", self.perform_search, "Press Enter to search for islands")
        
        # Add navigation buttons
        self.ui.add_button("Search", "Previous Page", self.previous_page, "Press Enter to go to previous page")
        self.ui.add_button("Search", "Next Page", self.next_page, "Press Enter to go to next page")

    def smooth_move_and_click(self, x: int, y: int, duration: float = 0.04) -> None:
        """Smoothly move to coordinates and click."""
        pyautogui.moveTo(x, y, duration=duration)
        pyautogui.click()

    def select_island(self, island: Dict) -> bool:
        """Perform the island selection sequence with fallback to name search."""
        try:
            # Click gamemode selection
            self.smooth_move_and_click(109, 67)
            time.sleep(0.5)

            # Click search field
            self.smooth_move_and_click(900, 200)
            time.sleep(0.1)

            # Clear previous text
            pyautogui.typewrite('\b' * 50, interval=0.01)

            # Check if we have a valid island code
            if self.is_valid_island_code(island['code']):
                # Use the code directly
                search_text = island['code']
            else:
                # Fall back to using the island name
                search_text = island['title']

            # Enter the search text
            pyautogui.write(search_text)
            pyautogui.press('enter')

            # Wait for white pixel indicator
            start_time = time.time()
            while not pyautogui.pixelMatchesColor(123, 327, (255, 255, 255)):
                if time.time() - start_time > 5:
                    return False
                time.sleep(0.1)
            time.sleep(0.1)

            # Complete selection sequence
            self.smooth_move_and_click(250, 436)
            time.sleep(0.7)
            self.smooth_move_and_click(285, 910)
            time.sleep(0.5)

            # Exit menus
            pyautogui.press('b', presses=2, interval=0.05)
            return True
            
        except Exception as e:
            print(f"Error selecting island: {str(e)}")
            return False

    def update_results_tab(self):
        """Update the Results tab with current search results."""
        # Clear existing widgets in Results tab
        self.ui.widgets["Results"] = []
        
        if not self.current_islands:
            self.ui.add_button("Results", "No islands found", lambda: None, "No islands were found for this search")
            return

        # Add island buttons
        for island in self.current_islands:
            players_text = f" ({island['playerCount']} players)" if island['playerCount'] > 0 else ""
            button_text = f"{island['title']}{players_text}"
            speech_text = f"{island['title']}. {island['description']}. {island['playerCount']} players online. Press Enter to select."
            
            self.ui.add_button(
                "Results",
                button_text,
                lambda i=island: self.select_island_action(i),
                speech_text
            )

    def select_island_action(self, island: Dict):
        """Handle island selection and provide feedback."""
        self.ui.root.destroy()
        success = self.select_island(island)
        if success:
            self.ui.speak(f"Selected {island['title']}")
        else:
            self.ui.speak("Failed to select island. Please try again.")

    def perform_search(self):
        """Execute the search and update results."""
        query = self.ui.variables["Search"]["Search Query"].get()
        if not query:
            self.ui.speak("Please enter a search query first")
            return

        self.current_query = query
        self.current_page = 1
        self.search_and_update()

    def search_and_update(self):
        """Perform search and update the UI."""
        self.current_islands, self.has_next_page = self.searcher.search_islands(
            self.current_query, 
            self.current_page
        )
        self.update_results_tab()
        
        # Update page navigation buttons
        self.ui.widgets["Search"][2].config(state='normal' if self.current_page > 1 else 'disabled')
        self.ui.widgets["Search"][3].config(state='normal' if self.has_next_page else 'disabled')
        
        # Switch to Results tab and focus first result
        self.ui.notebook.select(1)  # Select Results tab
        if self.ui.widgets["Results"]:
            self.ui.widgets["Results"][0].focus_set()

    def previous_page(self):
        """Go to previous page of results."""
        if self.current_page > 1:
            self.current_page -= 1
            self.search_and_update()

    def next_page(self):
        """Go to next page of results."""
        if self.has_next_page:
            self.current_page += 1
            self.search_and_update()

def launch_island_selector():
    """Launch the island selector GUI."""
    selector = IslandSelectorGUI()
    
    # Set up initial focus
    def focus_first_widget():
        if selector.ui.widgets["Search"]:
            first_widget = selector.ui.widgets["Search"][0]
            first_widget.focus_set()
            selector.ui.speak("Enter search query and press Enter to search")

    # Initialize window
    selector.ui.root.after(100, lambda: force_focus_window(
        selector.ui.root,
        "",
        focus_first_widget
    ))

    selector.ui.run()

if __name__ == "__main__":
    launch_island_selector()
