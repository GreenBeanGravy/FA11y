from lib.guis.AccessibleUIBackend import AccessibleUIBackend
import requests
import json
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import time
import pyautogui
from dataclasses import dataclass
import os
from lib.utilities import force_focus_window
import tkinter as tk
from tkinter import ttk, messagebox

@dataclass
class FavoriteIsland:
    title: str
    code: str
    description: str
    players: int

class FavoritesManager:
    def __init__(self, filename: str = "fav_islands.txt"):
        self.filename = filename
        self.favorites: List[FavoriteIsland] = []
        self.load_favorites()

    def load_favorites(self) -> None:
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
                    self.favorites = [FavoriteIsland(**island) for island in data]
            except json.JSONDecodeError:
                print("Error loading favorites file. Starting with empty favorites.")
                self.favorites = []
        else:
            self.favorites = []

    def save_favorites(self) -> None:
        with open(self.filename, 'w') as f:
            json.dump([vars(island) for island in self.favorites], f, indent=2)

    def toggle_favorite(self, island: Dict) -> bool:
        existing = next((f for f in self.favorites if f.code == island['code']), None)
        
        if existing:
            self.favorites.remove(existing)
            self.save_favorites()
            return False
        else:
            new_fav = FavoriteIsland(
                title=island['title'],
                code=island['code'],
                description=island.get('description', ''),
                players=island.get('playerCount', 0)
            )
            self.favorites.append(new_fav)
            self.save_favorites()
            return True

    def is_favorite(self, code: str) -> bool:
        return any(f.code == code for f in self.favorites)

    def get_favorites_as_dicts(self) -> List[Dict]:
        return [{
            'title': f.title,
            'code': f.code,
            'description': f.description,
            'playerCount': f.players
        } for f in self.favorites]

    def remove_all_favorites(self) -> None:
        self.favorites = []
        self.save_favorites()

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

    def clean_title(self, text: str) -> str:
        """Clean title by removing emojis and extra whitespace."""
        # Remove emoji characters
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        text = emoji_pattern.sub('', text)
        
        # Remove heart/special characters often used in titles
        text = re.sub(r'[💙❤️♥️💜💚💛🧡]', '', text)
        
        # Remove extra whitespace and normalize
        text = ' '.join(text.split())
        
        # Remove duplicate title occurrences
        parts = text.split(' - ')
        if len(parts) > 1 and parts[0].strip() == parts[1].strip():
            text = parts[0]
            
        return text.strip()

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
                        'title': self.clean_title(title),
                        'code': code,
                        'playerCount': 0,
                        'description': self.clean_title(item.get('snippet', ''))
                    }
                    islands.append(processed_item)
            else:
                for island in items:
                    title = self.clean_title(island.get('title', ''))
                    description = self.clean_title(island.get('imgAlt', ''))
                    
                    # If description is just repeating the title, clear it
                    if description == title:
                        description = ''
                        
                    processed_island = {
                        'title': title,
                        'code': island.get('islandCode', ''),
                        'playerCount': island.get('ccu', 0),
                        'description': description
                    }
                    islands.append(processed_island)
            
            return islands
        except Exception as e:
            print(f"Error extracting islands: {str(e)}")
            return []

    def search_islands(self, query: str, page: int = 1, lang: str = "en-US", max_retries: int = 20) -> Tuple[List[Dict], bool]:
        url = "https://www.fortnite.com/search"
        params = {
            'q': query,
            'lang': lang,
            'page': page
        }

        retries = 0
        while retries <= max_retries:
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

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403 and retries < max_retries:
                    print(f"403 error encountered, retry {retries + 1} of {max_retries}")
                    retries += 1
                    time.sleep(0.1)  # Add delay between retries
                else:
                    raise
            except Exception as e:
                print(f"Search error: {str(e)}")
                return [], False

        return [], False

class IslandSelectorGUI:
    def __init__(self):
        self.searcher = FortniteIslandSearch()
        self.favorites_manager = FavoritesManager()
        self.current_page = 1
        self.current_query = ""
        self.current_islands = []
        self.has_next_page = False
        self.ui = AccessibleUIBackend("Island Selector")
        self.setup_ui()

    def setup_ui(self):
        """Initialize the UI with search, results, and favorites tabs."""
        self.ui.add_tab("Search")
        self.ui.add_tab("Results")
        self.ui.add_tab("Favorites")
        
        # Add search entry
        self.ui.add_entry("Search", "Search Query")
        self.ui.add_button("Search", "Search", self.perform_search, "Press Enter to search for islands")
        
        # Add navigation buttons
        self.ui.add_button("Search", "Previous Page", self.previous_page, "Press Enter to go to previous page")
        self.ui.add_button("Search", "Next Page", self.next_page, "Press Enter to go to next page")

        # Initialize favorites tab
        self.update_favorites_tab()

    def show_remove_all_confirmation(self):
        confirmation = messagebox.askyesno(
            "Remove All Favorites",
            "Are you sure you want to remove all favorites?",
            parent=self.ui.root
        )
        if confirmation:
            self.favorites_manager.remove_all_favorites()
            self.update_favorites_tab()
            self.ui.speak("All favorites removed")
        else:
            self.ui.speak("Operation cancelled")

    def update_favorites_tab(self):
        """Update the Favorites tab with current favorites."""
        # Clear existing widgets in Favorites tab
        self.ui.widgets["Favorites"] = []
        
        favorites = self.favorites_manager.get_favorites_as_dicts()
        if not favorites:
            self.ui.add_button("Favorites", "No favorites saved", lambda: None, "No favorites have been saved yet")
            return

        for island in favorites:
            players_text = f" ({island['playerCount']} players)" if island['playerCount'] > 0 else ""
            button_text = f"⭐ {island['title']}{players_text}"
            
            speech_text = island['title']
            if island['description']:
                speech_text += f". {island['description']}"
            speech_text += f". {island['playerCount']} players online. Press Enter to select."
            
            self.ui.add_button(
                "Favorites",
                button_text,
                lambda i=island: self.select_island_action(i),
                speech_text
            )

    def handle_remove_all_favorites(self, event):
        """Handle the 'r' key press in favorites tab to remove all favorites."""
        if self.ui.notebook.index(self.ui.notebook.select()) == 2:  # Check if we're in the Favorites tab
            confirmation = messagebox.askyesno(
                "Remove All Favorites",
                "Are you sure you want to remove all favorites?",
                parent=self.ui.root
            )
            if confirmation:
                self.favorites_manager.remove_all_favorites()
                self.update_favorites_tab()
                self.ui.speak("All favorites removed")
            else:
                self.ui.speak("Operation cancelled")
        return "break"

    def handle_favorite_key(self, event):
        """Handle pressing the favorite key (f) for an island."""
        focused = self.ui.root.focus_get()
        if isinstance(focused, ttk.Button) and self.current_islands:
            try:
                button_text = focused['text'].replace('⭐ ', '')
                # First try to find the island in current_islands
                island = next((i for i in self.current_islands if i['title'] in button_text), None)
                
                # If not found in current_islands, check favorites
                if not island:
                    favorites = self.favorites_manager.get_favorites_as_dicts()
                    island = next((i for i in favorites if i['title'] in button_text), None)
                
                if island:
                    is_added = self.favorites_manager.toggle_favorite(island)
                    # Update the star on the current button
                    focused.configure(text=f"⭐ {button_text}" if is_added else button_text.replace('⭐ ', ''))
                    # Update favorites tab
                    self.update_favorites_tab()
                    
                    action = "added to" if is_added else "removed from"
                    self.ui.speak(f"{island['title']} {action} favorites")
                    
            except tk.TclError:
                pass

    def smooth_move_and_click(self, x: int, y: int, duration: float = 0.04) -> None:
        """Smoothly move to coordinates and click."""
        pyautogui.moveTo(x, y, duration=duration)
        pyautogui.click()

    def select_island(self, island: Dict) -> bool:
        """Perform the island selection sequence."""
        try:
            # Click gamemode selection
            self.smooth_move_and_click(109, 67)
            time.sleep(0.5)

            # Click search field
            self.smooth_move_and_click(1280, 200)
            time.sleep(0.1)

            # Clear existing text
            pyautogui.typewrite('\b' * 50, interval=0.01)

            # Check if code matches the expected format (1111-1111-1111)
            code_pattern = re.compile(r'^\d{4}-\d{4}-\d{4}$')
            if code_pattern.match(island['code']):
                text_to_type = island['code']
            else:
                text_to_type = island['title']

            # Enter the code or name
            pyautogui.write(text_to_type)
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

    def select_island_action(self, island: Dict):
        """Handle island selection and provide feedback."""
        self.ui.root.destroy()
        success = self.select_island(island)
        if success:
            self.ui.speak(f"Selected {island['title']}")
        else:
            self.ui.speak("Failed to select island. Please try again.")

    def clear_results(self):
        """Clear the results tab and its widgets."""
        # Clear existing widgets in Results tab
        for widget in self.ui.widgets["Results"]:
            widget.destroy()
        
        # Clear our widget list
        self.ui.widgets["Results"] = []
        self.current_islands = []
        
        # Force update the display
        self.ui.tabs["Results"].update()

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
            
            # Add star if favorited
            if self.favorites_manager.is_favorite(island['code']):
                button_text = f"⭐ {button_text}"
            
            # Create speech text that includes description only if it adds new information
            speech_text = island['title']
            if island['description'] and island['description'] != island['title']:
                speech_text += f". {island['description']}"
            speech_text += f". {island['playerCount']} players online. Press Enter to select."
            
            self.ui.add_button(
                "Results",
                button_text,
                lambda i=island: self.select_island_action(i),
                speech_text
            )

    def perform_search(self):
        """Execute the search and update results."""
        query = self.ui.variables["Search"]["Search Query"].get()
        if not query:
            self.ui.speak("Please enter a search query first")
            return

        # Clear results before starting new search
        self.clear_results()
        self.current_query = query
        self.current_page = 1
        self.search_and_update()

    def search_and_update(self):
        """Perform search and update the UI."""
        # Switch to Results tab before clearing
        self.ui.notebook.select(1)  # Select Results tab
        
        # Clear results before search
        self.clear_results()
        
        try:
            # Perform the search
            self.current_islands, self.has_next_page = self.searcher.search_islands(
                self.current_query, 
                self.current_page
            )
            self.update_results_tab()
            
            # Update page navigation buttons
            self.ui.widgets["Search"][2].config(state='normal' if self.current_page > 1 else 'disabled')
            self.ui.widgets["Search"][3].config(state='normal' if self.has_next_page else 'disabled')
            
            # Focus first result if available
            if self.ui.widgets["Results"]:
                self.ui.widgets["Results"][0].focus_set()
                
            # Announce results
            result_count = len(self.current_islands)
            if result_count > 0:
                self.ui.speak(f"Found {result_count} {'island' if result_count == 1 else 'islands'}")
            else:
                self.ui.speak("No islands found")
                
        except Exception as e:
            self.ui.speak(f"Error during search: {str(e)}")
            print(f"Search error: {str(e)}")

    def previous_page(self):
        """Go to previous page of results."""
        if self.current_page > 1:
            self.current_page -= 1
            self.search_and_update()
        else:
            self.ui.speak("Already on first page")

    def next_page(self):
        """Go to next page of results."""
        if self.has_next_page:
            self.current_page += 1
            self.search_and_update()
        else:
            self.ui.speak("No more pages")

    def run(self):
        """Start the application."""
        # Bind the favorite key
        self.ui.root.bind('f', self.handle_favorite_key)
        
        # Bind the remove all favorites key (only works in Favorites tab)
        self.ui.root.bind('r', self.handle_remove_all_favorites)
        
        def initial_setup():
            force_focus_window(self.ui.root, "")
            if self.ui.widgets["Search"]:
                self.ui.widgets["Search"][0].focus_set()
                self.ui.speak("Enter search query and press Enter to search")

        self.ui.root.after(100, initial_setup)
        self.ui.run()

def launch_island_selector():
    """Launch the island selector GUI."""
    selector = IslandSelectorGUI()
    selector.run()

if __name__ == "__main__":
    launch_island_selector()
