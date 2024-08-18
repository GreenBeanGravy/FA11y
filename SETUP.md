# FA11y:
This is a general installation guide for FA11y. If you want to get the usage information about FA11y and how to use its many features, please read the README on GitHub, which is the same one included when you run the updater. This message will be edited as the installation process changes. Here is also the latest [FA11y Feature Showcase](https://www.youtube.com/watch?v=uFaeOuXnKN8) on YouTube!

## How to install FA11y:
* Install the latest version of [Python](https://www.python.org/downloads/).
* Once the Python installation has completed, run the  `"updater.py"` script.
* The updater will download all required files from the FA11y GitHub, and installs all requirements! This also runs anytime you start FA11y, but if you would prefer it didn't, you can disable it from your `"config.txt"` file, or through the config GUI.
* Once the window closes itself, or states that it has completed, you can run `"FA11y.py"`, which needs to be open in the background in order to use accessibility features. And that’s it for installing `FA11y`! Feel free to open the previously mentioned "`README`" which should now be available in your `FA11y` directory. In order to use `FA11y`, you need to install Fortnite of course! There are some simple guides on how to set up `Legendary` and get Fortnite installed on your system below this message.

## Using Legendary:
Legendary is a command line interface for the Epic Games Launcher. You won't need the Epic Games launcher installed to use Legendary. In order to install Fortnite, follow these steps:
* Open a command line window in the directory of your `"Legendary.exe"` file, which should be your root `FA11y` folder. If Legendary did not get added to your system PATH automatically, you may need to begin all commands with "`.\`".
* Once you have opened the command line window, type the command `"Legendary auth"`. This will bring up a page to log into your Epic Games account, where you will need to log in to your Epic Games account, log in with another service, or create a new account. Additionally, you may be hit with an inaccessible hCaptcha at some point during the login process. This is being worked on, but in the mean time, you may need to get sighted assistance if you DO receieve this captcha.
* If after you successfully log in, you get a screen showing raw HTML code, copy the listed authorization token, without the quotations, to your clipboard, and paste it into the command line window. Otherwise, you can ignore this.
* Assuming everything went smoothly for you, you should now be logged into Legendary! You can easily check this by running the `"Legendary auth"` command again.

## Getting Fortnite:
* Go to [the following link](https://store.epicgames.com/en-US/p/fortnite) to open the Fortnite page on the Epic Games store website, which you should now already be logged into.
* Find and click on the `"GET"` button.
* Follow the prompts that appear near the bottom of the page.
* After you successfully have added Fortnite to your Epic Games account, you can now run the `"Fortnite_Installer.py"` script found in your `FA11y` directory! While the installer is running, you can use the keybinds: `"P"` to get the last progress update, `"-"` or  `"+"` to adjust the speed of progress update announcements, and `"ESCAPE"` to cancel the entire install process.
* After the installer has completed, you can now run either of the batch files that launch Fortnite, preferably, use the `"performance_fortnite_launcher.bat"` one for best performance.