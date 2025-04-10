# Wabbajack Fast Downloader 2

---

### 🚨 IMPORTANT WARNING 🚨

**Using this tool is a violation of Nexus Mods policy.** Automated downloading outside their official API or website methods can lead to restrictions or bans on your Nexus Mods account. The creator of this tool takes **no responsibility** for any consequences resulting from its use. **Proceed at your own risk.**

---

### How to Use (Updated Process)

1.  **Extract Mod List:**
    *   First, use the `"Extract"` button within the tool to process your Wabbajack mod list file (`.wabbajack`).

2.  **Enter Session ID:**
    *   You need to provide your `nexusmods_session` value in the `"YOUR NEXUS SESSIONID"` field.
    *   **Watch the Video:** Detailed instructions on how to find this value are in the video located in the `docs` folder provided with the tool.
    *   **One-Time Setup (Usually):** You typically only need to do this once. However, you **must** re-enter it if you log out of Nexus Mods, or if you log into your Nexus Mods account on a different device or browser.

3.  **🔒 NEVER Share Your Session ID:**
    *   Your `nexusmods_session` value is sensitive authentication data. Keep it private and secure. Sharing it compromises your Nexus Mods account.

4.  **Set Download Location:**
    *   Specify the folder where you want the mods to be downloaded.

5.  **Start Download:**
    *   Click the `"Download Batch"` button to begin.

---

### Key Updates & Features

*   **Download Resuming:** Close the program and restart it later; downloads will pick up where they left off.
*   **Hash Checking:** Verifies downloaded files are complete and not corrupted.
*   **No Duplicate Downloads:** The tool intelligently skips files you already have.
*   **Browserless Operation:** Downloads occur directly without needing a separate browser window open.
*   Includes various other improvements for stability and efficiency.

---

**Reminder:** For help finding your `nexusmods_session` value, please refer to the instructional video in the `docs` folder.



**Wabbajack Fast Downloader** is a tool designed to streamline the process of downloading mods for modlists generated by Wabbajack. It extracts mod IDs and file IDs from the Wabbajack modlist JSON file, generates download links, and opens these links in batches for efficient downloading.

> **Project Origin:** This project was inspired by the need for a faster mod downloading process for Wabbajack-generated modlists, originating from [this GitHub issue](https://github.com/parsiad/nexus-autodl/issues/17).

## How It Works

1. **Modlist Extraction:** Parses the JSON modlist file to extract mod IDs and file IDs, generating download links for each mod on Nexus Mods.
2. **Batch Download:** Opens the generated download links in batches using the `webbrowser` module to bypass download limits and speed up the process.


## Requirements

- [Python 3.x](https://www.python.org)
- [Tampermonkey](https://www.tampermonkey.net)
- [Tampermonkey plugin to remove Nexus Mods wait time](https://greasyfork.org/en/scripts/394039-nexus-no-wait)

## Executable Usage | GUI Usage

<img src="https://github.com/user-attachments/assets/1146b16e-8112-4d86-a8e3-42ea1c746d16" width="400" alt="preview">

1. Download the executable from [here](https://github.com/M1n-74316D65/Wabbajack-fast-downloader/releases)

2. Run the executable

3. Select the '*.wabbajack' modlist file

4. Click 'Extract'

5. Click 'Batch Download' to download links in batches

## Terminal Usage | CLI Usage

1. **Clone or Download Repository:**

   ```bash
   git clone https://github.com/M1n-74316D65/Wabbajack-fast-downloader.git
   ```

2. **Locate and Extract Modlist File:**

   The modlist file is located within the Wabbajack modlist package, e.g., `3.2.0.1\downloaded_mod_lists\wj-featured@@\_tpf-fo4.wabbajack`. Use tools like 7-Zip or PeaZip to extract it.

3. **Place Modlist File:**

   Place the extracted Wabbajack modlist JSON file in the project directory.

4. **Extract Modlist Data:**

   Run the script to generate download links:

   ```bash
   python extract_modlist.py
   ```

   This will create an `output.txt` file with the download links.

5. **Batch Download:**

   Run the batch download script to start downloading mods in batches:

   ```bash
   python batch_download.py
   ```

   The script will open download links in batches. Let the downloads complete, and press Enter in the terminal for the next batch.

## Acknowledgments

This project was inspired by the need for a faster mod downloading process for Wabbajack-generated modlists.

## Disclaimer

This tool is intended for personal use and should be used responsibly. Respect the terms and conditions of the mod authors and Nexus Mods. Use this tool at your own risk.

## ✨ Contributors

<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%">
        <a href="https://github.com/M1n-74316D65">
          <img src="https://avatars.githubusercontent.com/M1n-74316D65" width="100px;" alt="M1n-74316D65"/>
          <br />
          <sub><b>M1n-74316D65</b></sub>
        </a>
        <br />
        <a href="https://github.com/M1n-74316D65/Wabbajack-fast-downloader/commits?author=M1n-74316D65" title="Code">💻</a>
        <a href="https://github.com/M1n-74316D65/Wabbajack-fast-downloader/commits?author=M1n-74316D65" title="Documentation">📖</a>
      </td>
      <td align="center" valign="top" width="14.28%">
        <a href="https://github.com/DassaultMirage2K">
          <img src="https://avatars.githubusercontent.com/DassaultMirage2K" width="100px;" alt="DassaultMirage2K"/>
          <br />
          <sub><b>DassaultMirage2K</b></sub>
        </a>
        <br />
        <a href="https://github.com/M1n-74316D65/Wabbajack-fast-downloader/commits?author=DassaultMirage2K" title="Code">💻</a>
        <a href="https://github.com/M1n-74316D65/Wabbajack-fast-downloader/commits?author=DassaultMirage2K" title="Documentation">📖</a>
      </td>
    </tr>
  </tbody>
</table>

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<!-- markdownlint-enable -->
<!-- prettier-ignore-end -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

*This project follows the [all-contributors](https://allcontributors.org) specification*
