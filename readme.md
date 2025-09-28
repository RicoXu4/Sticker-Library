# Sticker Library

A self-hosted webapp for keeping all your stickers, memes, and random images in one searchable place.  
It’s designed to play nice with most messaging apps — basically your own private sticker vault ✨

---

## 🚧 Status

This is still under development.  
Future plans include:
- Better OCR accuracy (low-res memes, we’re looking at you 👀)
- Support for 3rd party OCR APIs
- Standalone desktop apps
- A Docker image for easy one-command deployment

So yeah, it’s a side project, not a polished SaaS product — expect fun surprises along the way

---

## 🚀 Getting Started

Clone the repo and set it up locally:

```bash
git clone https://github.com/RicoXu4/Sticker-Library.git
cd Sticker-Library
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You’ll need to start both the OCR backend and the Flask API.

In one terminal, run RapidOCR:

```bash
rapidocr_api -ip 0.0.0.0 -p 9005
```
Then in another terminal (with your venv activated), run the Flask app:

```bash
python3 api.py
```
Then visit http://localhost:8080 and start uploading stickers

---

## 🤝 Contributing

Wanna help? Awesome! Contributions are very welcome:
- Open an issue with your idea/bug
- Fork the repo
- Make a branch (git checkout -b feature/cool-thing)
- Commit, push, and open a Pull Request

Even silly feature ideas, bug reports, or memes are welcome 💜