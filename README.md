# Microsoft Courses Downloader

> *"Because clicking through 47 tiny units isn't learning—it's a workout for your mouse finger."*

---

## Why this tool exists

It’s 2 AM. Your Azure AI-103 exam is in three days. You’re on Microsoft Learn, clicking through 12 modules full of tiny units—each a separate page. Tabs pile up, progress vanishes, and that paragraph you read yesterday? Lost somewhere between Computer Vision and NLP.

Microsoft Learn is great for bite-sized, month-long strolls. For actual studying, searching, or offline reading it’s a click-maze designed by a button enthusiast.

So I built a tool that stitches all those scattered micro-units into a single, searchable HTML or PDF file per module—all the content, zero clicking, fully offline.

Now go pass that exam.

---

## What It Does

Microsoft Courses Downloader is a Python tool that extracts content from each module’s mini‑site in Microsoft Learn courses and turns it into clearly organized documents—one document per module.

- **Course Extraction**: Fetches learning paths and modules from any Microsoft Learn course URL
- **Learning Path Extraction**: Process any Microsoft Learn learning path URL directly
- **Module Extraction**: Process any Microsoft Learn module URL directly
- **Collection Extraction**: Process any Microsoft Learn collection URL, keeping each collection section in its own folder
- **Catalog API Integration**: Uses the official Microsoft Learn Catalog API for accurate course structure
- **Content Processing**: Extracts and cleans main content from course pages
- **HTML Generation**: Creates beautifully formatted, combined HTML files for each module
- **PDF Conversion**: Converts HTML files to PDF using Playwright
- **Organized Output**: Generates structured output with numbered directories and files

---

## Sample Output

![Sample output screenshot](screenshots/screen1.png)

---

## Prerequisites

- **Python 3.10 or higher** - [Download Python](https://www.python.org/downloads/)

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/MidnightFlux/microsoft-courses-downloader.git
cd microsoft-courses-downloader
```

### 2. Set Up Virtual Environment (Recommended)

Creating a virtual environment keeps dependencies isolated from your system Python.

#### Windows (PowerShell)

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1
```

> **Note**: If you get an execution policy error, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

#### Windows (Command Prompt)

```cmd
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate.bat
```

#### macOS / Linux

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

### 3. Install Dependencies

With the virtual environment activated (you should see `(.venv)` in your prompt):

```bash
pip install -r requirements.txt
```

### 4. Install Playwright Browsers

Playwright requires browser binaries for PDF generation:

> **Linux users**: Run this command first to install system dependencies:
> ```bash
> playwright install-deps
> ```

```bash
playwright install chromium
```

---

## Usage

### Running the Script

1. **Activate your virtual environment** (if not already active):
   - **Windows**: `.venv\Scripts\Activate.ps1` (or `activate.bat`)
   - **macOS/Linux**: `source .venv/bin/activate`

2. **Run the script**:

   ```bash
   python main.py
   ```

3. **Enter a URL** when prompted. The tool accepts four types of Microsoft Learn URLs:

   | URL Type | Example | Behavior |
   |---|---|---|
   | Course | `.../courses/ai-103t00` | Extracts all learning paths and their modules |
   | Learning Path | `.../training/paths/develop-generative-ai-apps/` | Extracts all modules in that learning path |
   | Module | `.../training/modules/prepare-azure-ai-development/` | Extracts all units in that single module |
   | Collection | `.../collections/p3zwhztxryzkqz` | Extracts every learning path, module, and course in the collection, section by section |

   Press Enter to use the default course URL (AI-103T00):

   ```
   Enter a Microsoft Learn course, learning path, module, or collection URL
    Course URL example: https://learn.microsoft.com/en-us/training/courses/ai-103t00
    Learning path URL example: https://learn.microsoft.com/en-us/training/paths/develop-generative-ai-apps/
    Module URL example: https://learn.microsoft.com/en-us/training/modules/prepare-azure-ai-development/
    Collection URL example: https://learn.microsoft.com/en-us/collections/p3zwhztxryzkqz
     (press Enter to use default course URL: https://learn.microsoft.com/en-us/training/courses/ai-103t00):
   > 
   ```

### Finding URLs

Browse all available Microsoft Learn courses at:  
**https://learn.microsoft.com/en-us/training/browse/?resource_type=course**

Copy any course, learning path, module, or collection URL and paste it when prompted.

### Output Structure by URL Type

- **Course URL** → `output/course-name/01-learning-path-name/01-module-name.pdf`
- **Learning Path URL** → `output/learning-path-name/01-module-name.pdf`
- **Module URL** → `output/module-name/01-module-name.pdf`
- **Collection URL** → `output/collection-name/01-section-name/01-learning-path-name/01-module-name.pdf`
  - A module saved directly in a section → `output/collection-name/01-section-name/02-module-name.pdf`
  - A course saved in a section → `output/collection-name/01-section-name/03-course-name/01-learning-path-name/01-module-name.pdf`
  - Items not in any section go in an `Other items` folder (or straight into the collection folder if it has no sections)
  - Other items (docs articles, videos, single unit pages) are skipped

---

## Example Output Structure

```
output/
├── course-title/
│   ├── 01-learning-path-name/
│   │   ├── 01-module-name.html
│   │   ├── 01-module-name.pdf
│   │   ├── 02-module-name.html
│   │   └── 02-module-name.pdf
│   ├── 02-learning-path-name/
│   │   ├── 01-module-name.html
│   │   ├── 01-module-name.pdf
│   │   └── ...
│   └── ...
└── ...
```

---

## 🎓 Study Tips

Want to supercharge your learning? Upload the generated PDFs to **[Google NotebookLM](https://notebooklm.google.com)**!

NotebookLM is an AI-powered research assistant that can:
- 🎙️ **Generate Podcasts** - Create AI-generated audio summaries you can listen to on the go
- ❓ **Create Quizzes** - Generate practice questions to test your understanding
- 🃏 **Build Flashcards** - Make study cards for quick review sessions
- 💬 **Answer Questions** - Ask questions about the course content and get instant answers
- 🔗 **Connect Ideas** - Discover relationships between different concepts in the material

Simply upload the PDF files generated by this tool to NotebookLM, and start exploring your course content in new, interactive ways!

---

## How It Works

1. **URL Detection**: The script detects whether you provided a course, learning path, module, or collection URL
2. **Catalog Fetching**: Fetches data from the Microsoft Learn Catalog API
   - For collection URLs, it also reads the collection's sections and items from the Microsoft Learn lists API (`https://learn.microsoft.com/api/lists/<collection-id>`)
3. **Learning Path Discovery** (course URLs only): Extracts all learning paths associated with the course
4. **Module Discovery** (course/learning path URLs): Resolves all modules for each learning path
5. **Unit Extraction**: Fetches all unit links within each module
6. **HTML Generation**: Combines all units into a single, styled HTML file per module
7. **PDF Conversion**: Uses Playwright to convert HTML files to PDF format

---

## Configuration

Default constants can be modified in `main.py`:

```python
DEFAULT_COURSE_URL = "https://learn.microsoft.com/en-us/training/courses/ai-103t00"
DEFAULT_LEARNING_PATH_URL = "https://learn.microsoft.com/en-us/training/paths/develop-generative-ai-apps/"
DEFAULT_MODULE_URL = "https://learn.microsoft.com/en-us/training/modules/prepare-azure-ai-development/"
DEFAULT_COLLECTION_URL = "https://learn.microsoft.com/en-us/collections/p3zwhztxryzkqz"
OUTPUT_BASE_DIR = "output"
PAGE_TITLE_IGNORE = ("Knowledge check", "Module assessment", "Exercise - ")
```

---

## Requirements

- Python 3.10+
- requests
- beautifulsoup4
- playwright

---

## License

MIT License
